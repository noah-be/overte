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
from conan_inventory import phase_inventory, verify_phase

SOURCE, MANIFEST, RECIPES = 'a' * 40, 'b' * 64, 'c' * 64


def graphs():
    # Declared-metadata fixture only, not evidence of an actual source build.
    package = dict(id='1', ref='openssl/3.5.8#' + 'd' * 32, rrev='d' * 32,
                   package_id='e' * 40, prev='f' * 32, context='host', binary='Build',
                   remote=None, binary_remote=None, settings={'os': 'Android', 'arch': 'armv8'},
                   options={'shared': 'True'}, license='Apache-2.0', dependencies={})
    actual = {'graph': {'nodes': {'0': {'id': '0', 'dependencies': {'1': {'ref': 'openssl/3.5.8'}}}, '1': package}}}
    expected = copy.deepcopy(actual); expected['graph']['nodes']['1']['prev'] = None
    return actual, expected


class ConanInventory(unittest.TestCase):
    def setUp(self):
        self.actual, self.expected = graphs()

    def check(self):
        return phase_inventory(self.actual, self.expected, SOURCE, 'target')

    def test_inventory_and_offline_cli_with_checkpoint(self):
        result = self.check()
        self.assertEqual(result['status'], 'CONAN_PHASE_BOUND_CONTENT_VERIFICATION_PENDING')
        self.assertEqual(len(result['packages']), 1)
        self.assertEqual(result['packages'][0]['prev'], 'f' * 32)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            actual, expected, checkpoint = (directory / name for name in ('actual.json', 'expected.json', 'target.COMPLETE'))
            actual.write_text(json.dumps(self.actual)); expected.write_text(json.dumps(self.expected))
            checkpoint.write_text('attempt_root=/attempt\nname=target\nsource_commit=' + SOURCE +
                                  '\nmanifest_sha256=' + MANIFEST + '\nrecipe_index_sha256=' + RECIPES +
                                  '\nresult_sha256=' + digest_file(actual) + '\njobs=7\n')
            arguments = (actual, expected, checkpoint, SOURCE, 'target', digest_file(expected), MANIFEST, RECIPES)
            bound = verify_phase(*arguments)
            self.assertEqual(bound['jobs'], 7)
            command = ['unshare', '--user', '--map-root-user', '--net', sys.executable,
                       str(ROOT / 'tools/sbom/verify-conan-phase.py'), '--actual-graph', str(actual),
                       '--expected-graph', str(expected), '--checkpoint', str(checkpoint), '--phase', 'target',
                       '--expected-source-sha', SOURCE, '--expected-graph-sha256', digest_file(expected),
                       '--expected-manifest-sha256', MANIFEST, '--expected-recipe-index-sha256', RECIPES]
            process = subprocess.run(command, capture_output=True, text=True, timeout=5)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(json.loads(process.stdout), bound)
            actual.write_text(actual.read_text() + ' ')
            with self.assertRaisesRegex(IdentityError, 'CONAN_CHECKPOINT_BINDING'): verify_phase(*arguments)
            expected.write_text(expected.read_text() + ' ')
            with self.assertRaisesRegex(IdentityError, 'CONAN_EXPECTED_GRAPH_HASH'): verify_phase(*arguments)

    def test_cache_remote_missing_prev_and_wrong_context(self):
        for key, value in (('binary', 'Cache'), ('binary_remote', 'foreign'), ('remote', 'foreign'),
                           ('prev', None), ('prev', 'wrong'), ('context', 'build')):
            with self.subTest(key=key):
                old = copy.deepcopy(self.actual)
                self.actual['graph']['nodes']['1'][key] = value
                with self.assertRaises(IdentityError): self.check()
                self.actual = old

    def test_locked_recipe_settings_options_license_and_package_id(self):
        for key, value in (('rrev', 'a' * 32), ('package_id', 'a' * 40), ('settings', {'os': 'Linux'}),
                           ('options', {'shared': 'False'}), ('license', 'MIT'), ('ref', 'foreign/1#' + 'd' * 32)):
            with self.subTest(key=key):
                old = copy.deepcopy(self.actual)
                self.actual['graph']['nodes']['1'][key] = value
                with self.assertRaisesRegex(IdentityError, 'CONAN_PINNED_PACKAGE_MISMATCH'): self.check()
                self.actual = old

    def test_missing_extra_and_dangling_nodes(self):
        self.actual['graph']['nodes'].pop('1')
        with self.assertRaises(IdentityError): self.check()
        self.actual, self.expected = graphs()
        self.actual['graph']['nodes']['2'] = self.actual['graph']['nodes']['1']
        with self.assertRaises(IdentityError): self.check()
        self.actual, self.expected = graphs()
        for graph in (self.actual, self.expected):
            graph['graph']['nodes']['1']['dependencies'] = {'99': {}}
        with self.assertRaisesRegex(IdentityError, 'CONAN_DEPENDENCIES'): self.check()

    def test_wrong_checkpoint_fields_and_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            actual, expected, checkpoint = (directory / name for name in ('a.json', 'e.json', 'c.COMPLETE'))
            actual.write_text(json.dumps(self.actual)); expected.write_text(json.dumps(self.expected))
            good = dict(attempt_root='/attempt', name='target', source_commit=SOURCE, manifest_sha256=MANIFEST,
                        recipe_index_sha256=RECIPES, result_sha256=digest_file(actual), jobs='7')
            arguments = (actual, expected, checkpoint, SOURCE, 'target', digest_file(expected), MANIFEST, RECIPES)
            for key, value in (('source_commit', 'f' * 40), ('name', 'host-tools'), ('manifest_sha256', 'f' * 64),
                               ('recipe_index_sha256', 'f' * 64), ('jobs', '0')):
                changed = dict(good, **{key: value})
                checkpoint.write_text(''.join(k + '=' + v + '\n' for k, v in changed.items()))
                with self.assertRaises(IdentityError): verify_phase(*arguments)
            checkpoint.write_text(''.join(k + '=' + v + '\n' for k, v in good.items()) + 'jobs=7\n')
            with self.assertRaises(IdentityError): verify_phase(*arguments)
            link = directory / 'link.COMPLETE'; link.symlink_to(checkpoint)
            with self.assertRaises(IdentityError): verify_phase(actual, expected, link, *arguments[3:])


if __name__ == '__main__':
    unittest.main()
