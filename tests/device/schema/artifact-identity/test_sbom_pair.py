# SPDX-License-Identifier: Apache-2.0
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'provenance'))
from artifact_identity import IdentityError
from sbom_validation import read_sbom, validate_pair

SOURCE, ARTIFACT = 'a' * 40, 'b' * 64


def fixture():
    # Format-only fixture. No actual Conan package, source archive or APK is claimed.
    def package(name, version, identity, purl):
        return dict(SPDXID=identity, name=name, versionInfo=version, downloadLocation='NOASSERTION',
                    filesAnalyzed=False, licenseConcluded='Apache-2.0', licenseDeclared='Apache-2.0',
                    copyrightText='NOASSERTION', externalRefs=[dict(referenceCategory='PACKAGE-MANAGER',
                    referenceType='purl', referenceLocator=purl)])
    def component(name, version, identity, purl, kind='library'):
        return {'type': kind, 'bom-ref': identity, 'name': name, 'version': version, 'purl': purl,
                'licenses': [{'license': {'id': 'Apache-2.0'}}]}
    root = package('overte-phone', '1', 'SPDXRef-App', 'pkg:generic/overte-phone@1')
    dependency = package('openssl', '3.5.8', 'SPDXRef-OpenSSL', 'pkg:conan/openssl@3.5.8')
    root['sourceInfo'] = 'overte-source-revision:' + SOURCE
    root['checksums'] = [dict(algorithm='SHA256', checksumValue=ARTIFACT)]
    spdx = dict(spdxVersion='SPDX-2.3', dataLicense='CC0-1.0', SPDXID='SPDXRef-DOCUMENT',
                name='overte-sbom-fixture', documentNamespace='https://spdx.org/spdxdocs/overte-fixture-6d326c42',
                creationInfo=dict(creators=['Tool: overte-fixture'], created='2026-09-06T00:00:00Z'),
                packages=[root, dependency], relationships=[
                    dict(spdxElementId='SPDXRef-DOCUMENT', relationshipType='DESCRIBES', relatedSpdxElement='SPDXRef-App'),
                    dict(spdxElementId='SPDXRef-App', relationshipType='DEPENDS_ON', relatedSpdxElement='SPDXRef-OpenSSL')])
    root = component('overte-phone', '1', 'app', 'pkg:generic/overte-phone@1', 'application')
    root['properties'] = [dict(name='overte:sourceRevision', value=SOURCE)]
    root['hashes'] = [dict(alg='SHA-256', content=ARTIFACT)]
    cyclone = dict(bomFormat='CycloneDX', specVersion='1.6', version=1, metadata=dict(component=root),
                   components=[component('openssl', '3.5.8', 'openssl', 'pkg:conan/openssl@3.5.8')],
                   dependencies=[{'ref': 'app', 'dependsOn': ['openssl']}, {'ref': 'openssl', 'dependsOn': []}])
    return spdx, cyclone


class SbomPair(unittest.TestCase):
    def setUp(self):
        self.spdx, self.cyclone = fixture()

    def check(self):
        return validate_pair(self.spdx, self.cyclone, SOURCE, ARTIFACT)

    def test_formats_pair_and_actual_offline_cli(self):
        result = self.check()
        self.assertEqual(result['status'], 'SBOM_PAIR_VALID_CONTENT_VERIFICATION_PENDING')
        self.assertEqual((result['packages'], result['dependencies']), (2, 1))
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            spdx, cdx = directory / 'spdx.json', directory / 'cdx.json'
            spdx.write_text(json.dumps(self.spdx)); cdx.write_text(json.dumps(self.cyclone))
            command = ['unshare', '--user', '--map-root-user', '--net', sys.executable,
                       str(ROOT / 'tools/sbom/verify-sbom-pair.py'), '--spdx', str(spdx), '--cyclonedx', str(cdx),
                       '--expected-source-sha', SOURCE, '--expected-artifact-sha256', ARTIFACT]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout), result)
            self.spdx['packages'][0]['checksums'][0]['checksumValue'] = 'f' * 64
            self.spdx['packages'][0]['name'] = 'private-canary-do-not-emit'
            spdx.write_text(json.dumps(self.spdx))
            rejected = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertNotIn('private-canary', rejected.stdout + rejected.stderr)

    def test_real_format_validators_reject_invalid_documents(self):
        for document, key, value in ((self.spdx, 'dataLicense', 'MIT'),
                                     (self.spdx, 'unknown-private-field', True),
                                     (self.spdx, 'spdxVersion', 'SPDX-3.0'),
                                     (self.cyclone, 'specVersion', '1.5'),
                                     (self.cyclone, 'serialNumber', 'invalid-not-a-uuid-urn'),
                                     (self.cyclone, 'unknown-private-field', True)):
            with self.subTest(key=key):
                original = copy.deepcopy(document)
                document[key] = value
                with self.assertRaises(IdentityError): self.check()
                document.clear(); document.update(original)

    def test_package_version_license_and_duplicate_join(self):
        for key, value in (('version', '3.5.7'), ('name', 'foreign'),
                           ('licenses', [{'license': {'id': 'MIT'}}]), ('purl', 'pkg:conan/openssl@3.5.7')):
            with self.subTest(key=key):
                old = copy.deepcopy(self.cyclone['components'][0])
                self.cyclone['components'][0][key] = value
                with self.assertRaises(IdentityError): self.check()
                self.cyclone['components'][0] = old
        self.cyclone['components'].append(copy.deepcopy(self.cyclone['components'][0]))
        with self.assertRaises(IdentityError): self.check()

    def test_wrong_source_artifact_and_root(self):
        for source, artifact in (('c' * 40, ARTIFACT), (SOURCE, 'c' * 64)):
            with self.assertRaises(IdentityError): validate_pair(self.spdx, self.cyclone, source, artifact)
        self.spdx['relationships'][0]['relatedSpdxElement'] = 'SPDXRef-OpenSSL'
        with self.assertRaises(IdentityError): self.check()

    def test_dependency_mismatch_dangling_and_disconnected(self):
        self.cyclone['dependencies'][0]['dependsOn'] = []
        with self.assertRaises(IdentityError): self.check()
        self.spdx['relationships'].pop()
        with self.assertRaisesRegex(IdentityError, 'SBOM_DISCONNECTED_PACKAGE'): self.check()
        self.cyclone['dependencies'][0]['dependsOn'] = ['missing']
        with self.assertRaises(IdentityError): self.check()

    def test_duplicate_nonfinite_and_symlink_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'sbom.json'
            for value in ('{"x":1,"x":2}', '{"x":NaN}', '[]'):
                path.write_text(value)
                with self.assertRaises(IdentityError): read_sbom(path)
            link = path.with_name('link.json'); link.symlink_to(path)
            with self.assertRaises(IdentityError): read_sbom(link)

    def test_profile_collections_are_bounded_before_schema_traversal(self):
        self.spdx['packages'] = [{}] * 4097
        with self.assertRaisesRegex(IdentityError, 'SBOM_COLLECTION_LIMIT'): self.check()

    def test_agreeing_documents_cannot_contradict_purl_identity(self):
        self.spdx['packages'][1]['versionInfo'] = '3.5.7'
        self.cyclone['components'][0]['version'] = '3.5.7'
        with self.assertRaisesRegex(IdentityError, 'SBOM_PURL_IDENTITY'): self.check()
        self.spdx, self.cyclone = fixture()
        self.cyclone['components'] = [{}] * 4096
        with self.assertRaisesRegex(IdentityError, 'SBOM_COLLECTION_LIMIT'): self.check()


if __name__ == '__main__':
    unittest.main()
