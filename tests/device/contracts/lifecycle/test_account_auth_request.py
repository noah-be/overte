"""Five complete original credential request methods at the real Qt POST seam."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from test_login_dialog_domain_receiver import block

ROOT = Path(__file__).resolve().parents[4]


class AccountRequest(unittest.TestCase):
    def test_no_provider_connection_to_absent_login_error_slot(self):
        header = (ROOT / 'libraries/networking/src/AccountManager.h').read_text()
        source = (ROOT / 'libraries/networking/src/AccountManager.cpp').read_text()
        # Main has no such production slot. A fixture must not invent it to
        # conceal string-based connections which Qt cannot bind at runtime.
        self.assertNotIn('requestAccessTokenError(', header)
        for name in ('requestAccessTokenWithSteam', 'requestAccessTokenWithOculus'):
            method = block(source, 'void AccountManager::' + name + '(')
            self.assertNotIn('SLOT(requestAccessTokenError(', method)
            self.assertIn('&AccountManager::requestAccessTokenFinished', method)

    def test_original_form_fields_redirect_policy_and_receiver_wiring(self):
        baseline = os.environ.get('OVERTE_ACCOUNT_REQUEST_BASELINE')
        relative = 'libraries/networking/src/AccountManager.cpp'
        source = (subprocess.check_output(['git', '-C', str(ROOT), 'show', baseline + ':' + relative],
                  text=True) if baseline else (ROOT / relative).read_text())
        methods = '\n'.join(block(source, 'void AccountManager::' + name + '(') for name in
                            ('requestAccessToken', 'requestAccessTokenWithAuthCode',
                             'requestAccessTokenWithSteam', 'requestAccessTokenWithOculus',
                             'refreshAccessToken'))
        marker = 'static void observeAccountTokenDeadline('
        if marker in source:
            methods = block(source, marker) + '\n' + methods
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Network'], text=True))
        moc = Path(subprocess.check_output(['pkg-config', '--variable=libexecdir', 'Qt6Core'], text=True).strip()) / 'moc'
        here = Path(__file__).parent
        with tempfile.TemporaryDirectory(prefix='overte-account-request-') as temporary:
            scratch = Path(temporary)
            (scratch / 'requests.inc').write_text(methods)
            subprocess.run([str(moc), str(here / 'account-auth-request-test.cpp'),
                            '-o', str(scratch / 'requests.moc')], check=True, timeout=15)
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), '-I', str(scratch),
                            str(here / 'account-auth-request-test.cpp'), '-o', str(binary), *flags],
                           check=True, timeout=30)
            subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary)],
                           check=True, timeout=25)


if __name__ == '__main__':
    unittest.main()
