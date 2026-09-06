"""Actual login/loginDomain/signup bodies and actual Phone pending-request guard."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


class LoginDialogDiagnostics(unittest.TestCase):
    def test_original_credentials_and_phone_guard_without_raw_logs(self):
        source = (ROOT / 'interface/src/ui/LoginDialog.cpp').read_text()
        methods = []
        for name in ('login', 'loginDomain', 'signup'):
            start = source.index('void LoginDialog::' + name + '(')
            end = source.index('\n}', start) + 2
            methods.append(source[start:end])
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Network'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-login-privacy-') as temporary:
            directory = pathlib.Path(temporary)
            (directory / 'login-methods.inc').write_text('\n'.join(methods))
            variant = os.environ.get('OVERTE_LOGIN_VARIANT', 'main')
            self.assertIn(variant, ('main', 'apple'))
            for phone, ios in ((0, 0), (1, 0), (0, 1)):
                with self.subTest(phone=phone, ios=ios, variant=variant):
                    binary = directory / ('login-' + str(phone) + str(ios))
                    subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), '-I', str(directory),
                                    '-DTEST_PHONE=' + str(phone), '-DTEST_IOS=' + str(ios),
                                    '-DTEST_EXPECT_GUARD=' + str(int(phone or (ios and variant == 'apple'))),
                                    str(pathlib.Path(__file__).with_name('login-dialog-diagnostics-test.cpp')),
                                    '-o', str(binary), *flags], check=True, timeout=30)
                    subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary)], check=True, timeout=5)


if __name__ == '__main__':
    unittest.main()
