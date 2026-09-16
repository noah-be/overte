"""Real canonical adapter_call and child processes; no devices or adapter forks."""
import importlib.util
import os
from pathlib import Path
import sys
import traceback
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('shared_adapter_privacy', ROOT / 'run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class AdapterErrorPrivacy(unittest.TestCase):
    def assert_private_failure(self, command, **kwargs):
        try:
            runner.adapter_call(command, 'describe', 'private-selector-canary', **kwargs)
        except RuntimeError as error:
            self.assertEqual(str(error), 'OVT_TEST_INFRASTRUCTURE_ERROR')
            # Traceback frames naturally include this test's source; inspect the
            # formatted production exception tail, including any chained cause.
            self.assertIsNone(error.__cause__)
            if error.__context__ is not None:
                self.assertTrue(error.__suppress_context__)
            tail = ''.join(traceback.format_exception_only(type(error), error))
            self.assertNotIn('canary', tail)
        else:
            self.fail('expected infrastructure failure')

    def test_unlisted_encoded_split_and_nonzero_payloads(self):
        code = ('import os,sys; '
                'os.write(1,b"stdout-secret-canary"); '
                'os.write(2,b"token-private-canary c2VjcmV0LWNhbmFyeQ== split-"); '
                'os.write(2,b"secret-canary"); sys.exit(9)')
        self.assert_private_failure([sys.executable, '-c', code])

    def test_timeout_does_not_export_argv(self):
        self.assert_private_failure([sys.executable, '-c', 'import time; time.sleep(2)'], timeout=0.03)

    def test_missing_executable_does_not_export_path(self):
        self.assert_private_failure(['/nonexistent/private-executable-canary'])

    def test_invalid_json_and_invalid_utf8_are_private_failures(self):
        for code in ('print("private-json-canary")', 'import os; os.write(1,b"\\xff")'):
            with self.subTest(code=code):
                self.assert_private_failure([sys.executable, '-c', code])

    def test_success_returns_original_json_but_discards_stderr(self):
        for action in ('discover', 'describe', 'cleanup'):
            with self.subTest(action=action):
                code = ('import os; os.write(2,b"private-success-canary"); '
                        'print(\'{"ready":true,"count":2}\')')
                self.assertEqual({'ready': True, 'count': 2},
                                 runner.adapter_call([sys.executable, '-c', code], action))


if __name__ == '__main__':
    unittest.main()
