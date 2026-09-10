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
from artifact_identity import IdentityError, digest_file
from conan_inventory import phase_inventory
from conan_sources import join_sources, verify_sources
from test_conan_inventory import graphs, SOURCE, RECIPES


def closure():
    # Synthetic declared metadata; no claim this fixture built a package.
    return {'schema_version': 1, 'node_count': 1, 'recipe_export_index': {'sha256': RECIPES},
            'nodes': [{'reference': 'openssl/3.5.8', 'recipe_revision': 'd' * 32,
                       'classification': 'source-bearing', 'contexts': [{'graph': 'target'}],
                       'recipe': {'path': 'recipes/openssl/conanfile.py', 'sha256': '1' * 64,
                                  'exported_files': {'recipes/openssl/conanfile.py': '1' * 64}},
                       'sources': [{'id': 'openssl-source', 'sha256': '2' * 64,
                                    'canonical_url': 'https://source.example.invalid/openssl.tar.gz',
                                    'license': {'path': 'LICENSE', 'sha256': '3' * 64,
                                                'spdx': 'Apache-2.0'}}]}]}


class ConanSources(unittest.TestCase):
    def setUp(self):
        actual, expected = graphs()
        self.inventory = phase_inventory(actual, expected, SOURCE, 'target')
        self.inventory['recipeIndexSha256'] = RECIPES
        self.closure = closure()

    def test_source_and_virtual_mapping_and_literal_license_labels(self):
        result = join_sources(self.inventory, self.closure)
        self.assertEqual(result['status'], 'CONAN_SOURCE_METADATA_BOUND_PAYLOAD_VERIFICATION_PENDING')
        package = result['packages'][0]
        self.assertEqual(package['prev'], 'f' * 32)
        self.assertEqual(package['sourceObjects'][0]['licenseSha256'], '3' * 64)
        # Labels must not be laundered into asserted SPDX expressions.
        self.closure['nodes'][0]['sources'][0]['license']['spdx'] = 'MIT plus bundled notices'
        self.assertEqual(join_sources(self.inventory, self.closure)['packages'][0]['sourceObjects'][0]
                         ['declaredLicenseLabel'], 'MIT plus bundled notices')
        node = self.closure['nodes'][0]
        node.update(classification='virtual-system', sources=[],
                    system_binding={'provider': 'declared system boundary',
                                    'toolchain_path': 'toolchain.json', 'toolchain_sha256': '4' * 64})
        result = join_sources(self.inventory, self.closure)
        self.assertEqual(result['packages'][0]['sourceObjects'], [])
        self.assertEqual(result['packages'][0]['systemBinding']['toolchainSha256'], '4' * 64)
        del node['system_binding']
        with self.assertRaisesRegex(IdentityError, 'SOURCE_SYSTEM_BINDING'):
            join_sources(self.inventory, self.closure)

    def test_missing_duplicate_wrong_recipe_and_phase(self):
        for key, value in (('reference', 'foreign/1'), ('recipe_revision', 'a' * 32),
                           ('contexts', [{'graph': 'bootstrap'}]), ('classification', 'virtual-system'),
                           ('sources', [])):
            changed = copy.deepcopy(self.closure); changed['nodes'][0][key] = value
            with self.subTest(key=key), self.assertRaises(IdentityError): join_sources(self.inventory, changed)
        self.closure['nodes'].append(copy.deepcopy(self.closure['nodes'][0])); self.closure['node_count'] = 2
        with self.assertRaisesRegex(IdentityError, 'SOURCE_REFERENCE'): join_sources(self.inventory, self.closure)
        self.closure = closure(); self.closure['recipe_export_index']['sha256'] = 'f' * 64
        with self.assertRaisesRegex(IdentityError, 'SOURCE_RECIPE_INDEX'): join_sources(self.inventory, self.closure)

    def test_unsafe_paths_malformed_digests_and_duplicate_sources(self):
        for path in ('/absolute/LICENSE', '../LICENSE', 'a/../LICENSE', 'a\\LICENSE', 'a//LICENSE'):
            changed = copy.deepcopy(self.closure)
            changed['nodes'][0]['sources'][0]['license']['path'] = path
            with self.subTest(path=path), self.assertRaisesRegex(IdentityError, 'SOURCE_LEDGER_PATH'):
                join_sources(self.inventory, changed)
        for key in ('sha256', 'canonical_url'):
            changed = copy.deepcopy(self.closure); changed['nodes'][0]['sources'][0][key] = 'invalid'
            with self.assertRaises(IdentityError): join_sources(self.inventory, changed)
        self.closure['nodes'][0]['sources'].append(copy.deepcopy(self.closure['nodes'][0]['sources'][0]))
        with self.assertRaisesRegex(IdentityError, 'SOURCE_OBJECT_IDENTITY'): join_sources(self.inventory, self.closure)
        changed = closure(); changed['nodes'][0]['recipe']['sha256'] = '7' * 64
        with self.assertRaisesRegex(IdentityError, 'SOURCE_RECIPE_MAIN'): join_sources(self.inventory, changed)

    def test_actual_offline_cli_revalidates_phase_and_independent_closure_digest(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            actual, expected, manifest, checkpoint = (directory / name for name in
                                                      ('actual.json', 'expected.json', 'sources.json', 'target.COMPLETE'))
            graph, pinned = graphs()
            actual.write_text(json.dumps(graph)); expected.write_text(json.dumps(pinned))
            manifest.write_text(json.dumps(self.closure))
            manifest_hash = digest_file(manifest)
            checkpoint.write_text('attempt_root=/attempt\nname=target\nsource_commit=' + SOURCE +
                                  '\nmanifest_sha256=' + manifest_hash + '\nrecipe_index_sha256=' + RECIPES +
                                  '\nresult_sha256=' + digest_file(actual) + '\njobs=7\n')
            arguments = (manifest, actual, expected, checkpoint, SOURCE, 'target',
                         digest_file(expected), manifest_hash, RECIPES)
            result = verify_sources(*arguments)
            command = ['unshare', '--user', '--map-root-user', '--net', sys.executable,
                       str(ROOT / 'tools/sbom/join-conan-sources.py'), '--source-closure', str(manifest),
                       '--actual-graph', str(actual), '--expected-graph', str(expected), '--checkpoint', str(checkpoint),
                       '--phase', 'target', '--expected-source-sha', SOURCE, '--expected-graph-sha256', digest_file(expected),
                       '--expected-manifest-sha256', manifest_hash, '--expected-recipe-index-sha256', RECIPES]
            process = subprocess.run(command, capture_output=True, text=True, timeout=5)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(json.loads(process.stdout), result)
            manifest.write_text(manifest.read_text() + ' ')
            with self.assertRaisesRegex(IdentityError, 'SOURCE_CLOSURE_HASH'): verify_sources(*arguments)
            process = subprocess.run(command, capture_output=True, text=True, timeout=5)
            self.assertEqual(process.returncode, 1)
            self.assertEqual(process.stdout, '')
            self.assertEqual(process.stderr.strip(), 'SOURCE_CLOSURE_HASH')


if __name__ == '__main__':
    unittest.main()
