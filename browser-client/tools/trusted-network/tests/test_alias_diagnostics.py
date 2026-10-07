# SPDX-License-Identifier: Apache-2.0
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('alias_provenance', HERE / 'workflow/alias_diagnostics.py')
D = importlib.util.module_from_spec(spec)
spec.loader.exec_module(D)
spec = importlib.util.spec_from_file_location('alias_actual_build', HERE / 'workflow/build.py')
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)


def elf(name=b'libpython3.12.so.1.0'):
    result = bytearray(4096)
    result[:7] = b'\x7fELF\x02\x01\x01'
    struct.pack_into('<Q', result, 32, 64)
    struct.pack_into('<HH', result, 54, 56, 2)
    struct.pack_into('<IIQQQQQQ', result, 64, 1, 4, 0, 0x400000, 0, len(result), len(result), 4096)
    struct.pack_into('<IIQQQQQQ', result, 120, 2, 4, 256, 0x400100, 0, 80, 80, 8)
    for i, item in enumerate(((5, 0x400300), (10, 128), (1, 0), (29, 60), (0, 0))):
        struct.pack_into('<QQ', result, 256 + 16 * i, *item)
    result[768:768+len(name)+1] = name + b'\0'
    return bytes(result)


class AliasObservation(unittest.TestCase):
    def parse(self, data, name='libpython3.12.so.1.0'):
        with tempfile.TemporaryFile() as file:
            file.write(data); file.flush()
            return D.elf_direct_needed(file.fileno(), name)

    def test_lexical_config_link_and_canonical_library_are_distinct_fixed_classes(self):
        lexical = D.path_class('/usr/lib/python3.12/config-3.12-x86_64-linux-gnu/libpython3.12.so')
        canonical = D.path_class('/usr/lib/x86_64-linux-gnu/libpython3.12.so.1.0')
        self.assertEqual(lexical, {'nameClass': 'python312-shared-link-name', 'directoryClass': 'python312-config-directory'})
        self.assertEqual(canonical, {'nameClass': 'python312-shared-library-name', 'directoryClass': 'usr-library-directory'})

    def test_dynamic_table_direct_dependency_and_absence_preserve_no_mapped_claim(self):
        self.assertTrue(self.parse(elf())['canonicalLibraryNameNeeded'])
        value = self.parse(elf(b'libc.so.6'))
        self.assertFalse(value['canonicalLibraryNameNeeded'])
        self.assertEqual(value['neededCount'], 1)
        self.assertEqual(value['status'], 'elf-direct-dependency-only')
        self.assertTrue(value['runpathPresent'])
        self.assertLessEqual(value['readBytes'], 262144)

    def test_malformed_elf_table_range_and_string_bounds_refuse_without_exec(self):
        cases = [b'secret', bytearray(elf()), bytearray(elf()), bytearray(elf())]
        struct.pack_into('<H', cases[1], 56, 129)
        struct.pack_into('<Q', cases[2], 256+16+8, 65537)
        struct.pack_into('<Q', cases[3], 256+32+8, 4000)
        for data in cases:
            with self.subTest(case=cases.index(data)), self.assertRaises(ValueError):
                self.parse(data)

    def test_package_record_only_fixed_known_owner_and_bounded_ascii_version(self):
        outputs = [b'libpython3.12t64:amd64: /usr/lib/owned\n', b'3.12.3-1ubuntu0.17']
        with patch.object(D.subprocess, 'run', side_effect=[subprocess.CompletedProcess([],0,out) for out in outputs]) as run:
            value = D.package_owner('/usr/lib/owned')
        self.assertEqual(value, {'status': 'installed-metadata-only', 'name': 'libpython3.12t64', 'version': '3.12.3-1ubuntu0.17'})
        self.assertEqual(run.call_count, 2)
        self.assertTrue(all(call.kwargs['timeout'] == 2 for call in run.call_args_list))

    def test_unknown_duplicate_package_oversize_or_private_version_refuses(self):
        for raw in (b'private-account: /secret\n', b'x'*8193, b'libpython3.12t64: /x\nlibpython3.12-dev: /x\n'):
            with patch.object(D.subprocess,'run',return_value=subprocess.CompletedProcess([],0,raw)):
                value = D.package_owner('/usr/lib/owned')
            self.assertEqual(value['status'], 'not-observed')
            self.assertNotIn('private-account', json.dumps(value))
        with patch.object(D.subprocess,'run',side_effect=[subprocess.CompletedProcess([],0,b'libpython3.12t64: /usr/lib/owned\n'),subprocess.CompletedProcess([],0,b'3.12\ncredential')]):
            self.assertEqual(D.package_owner('/usr/lib/owned')['status'],'not-observed')

    def test_unknown_alias_or_private_input_does_not_query_tools_or_export_path(self):
        for name in ('/usr/lib/unknown', '/private/credential'):
            with patch.object(D.subprocess,'run') as run:
                value = D.observe_alias('/usr/bin/python3.12',name,name)
                run.assert_not_called()
            self.assertNotIn(name,json.dumps(value))
            self.assertFalse(value['admissionChanged'])
            self.assertFalse(value['packageSignatureVerified'])

    def run_refusal(self, enabled, *, earlier_success=False):
        error = B.TrustRefusal('python-import-alias-target-untrusted')
        returned = subprocess.CompletedProcess([], 0, b'["/usr/lib/python3.12"]')
        links = ['first', 'second'] if earlier_success else ['first']
        resolved = '/usr/lib/x86_64-linux-gnu/libpython3.12.so.1.0'
        records = [{'path': resolved, 'bytes': 1, 'sha256': 'a' * 64}, error] if earlier_success else [error]
        with patch.dict(os.environ, {'OVERTE_TRUSTED_ALIAS_DIAGNOSTICS': '1' if enabled else '0'}), \
             patch.object(B.subprocess, 'run', return_value=returned), \
             patch.object(Path, 'exists', return_value=True), patch.object(Path, 'is_dir', return_value=True), \
             patch.object(Path, 'resolve', lambda p, **k: p), patch.object(Path, 'is_file', return_value=True), \
             patch.object(Path, 'lstat', return_value=SimpleNamespace(st_mode=0o120777, st_uid=0)), \
             patch.object(B, 'rooted', side_effect=lambda p: str(p)), \
             patch.object(B.os, 'walk', return_value=[('/usr/lib/python3.12', [], links)]), \
             patch.object(B, 'rooted_alias', return_value=resolved), \
             patch.object(B, 'alias_record', side_effect=records) as checker, \
             patch('builtins.print') as output:
            with self.assertRaises(B.TrustRefusal) as raised:
                B.trusted_import_paths('/usr/bin/python3.12')
            self.assertIs(raised.exception, error)
            self.assertEqual(raised.exception.args, ('python-import-alias-target-untrusted',))
            self.assertEqual(checker.call_count, len(links))
            return output.call_args_list

    def test_actual_source_default_off_preserves_original_exception_and_no_observer(self):
        self.assertEqual(self.run_refusal(False), [])

    def test_actual_source_opt_in_observes_only_after_original_failure_never_retries(self):
        output = self.run_refusal(True)
        self.assertEqual(len(output), 1)
        self.assertTrue(output[0].args[0].startswith('TRUSTED_ALIAS_PROVENANCE:'))
        self.assertNotIn('/usr/', output[0].args[0])
        self.assertFalse(json.loads(output[0].args[0].split(':', 1)[1])['admissionChanged'])

    def test_actual_source_prior_valid_alias_cannot_relabel_later_chain_refusal(self):
        error = B.TrustRefusal('python-import-alias-chain-untrusted')
        returned = subprocess.CompletedProcess([], 0, b'["/usr/lib/python3.12"]')
        first = '/usr/lib/x86_64-linux-gnu/libpython3.12.so.1.0'
        with patch.dict(os.environ, {'OVERTE_TRUSTED_ALIAS_DIAGNOSTICS': '1'}), \
             patch.object(B.subprocess, 'run', return_value=returned), \
             patch.object(Path, 'exists', return_value=True), patch.object(Path, 'is_dir', return_value=True), \
             patch.object(Path, 'resolve', lambda p, **k: p), patch.object(Path, 'is_file', return_value=True), \
             patch.object(Path, 'lstat', return_value=SimpleNamespace(st_mode=0o120777, st_uid=0)), \
             patch.object(B, 'rooted', side_effect=lambda p: str(p)), \
             patch.object(B.os, 'walk', return_value=[('/usr/lib/python3.12', [], ['first', 'second'])]), \
             patch.object(B, 'rooted_alias', side_effect=[first, error]), \
             patch.object(B, 'alias_record', return_value={'path': first, 'bytes': 1, 'sha256': 'a' * 64}), \
             patch('builtins.print') as output:
            with self.assertRaises(B.TrustRefusal) as raised:
                B.trusted_import_paths('/usr/bin/python3.12')
            self.assertIs(raised.exception, error)
            output.assert_not_called()


if __name__ == '__main__':
    unittest.main()
