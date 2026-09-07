"""Actual logout/URL/request/completion methods and original RequestScope."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from test_login_dialog_domain_receiver import block

ROOT = Path(__file__).resolve().parents[4]


class AccountContext(unittest.TestCase):
    def test_original_context_changes_cannot_revive_old_credentials(self):
        baseline = os.environ.get('OVERTE_ACCOUNT_CONTEXT_BASELINE')
        relative = 'libraries/networking/src/AccountManager.cpp'
        source = (subprocess.check_output(['git', '-C', str(ROOT), 'show', baseline + ':' + relative],
                  text=True) if baseline else (ROOT / relative).read_text())
        methods = block(source, 'static void observeAccountTokenDeadline(') + '\n'
        methods += '\n'.join(block(source, 'void AccountManager::' + name + '(') for name in
                             ('logout', 'setAuthURL', 'setAccountInfo', 'requestAccessToken', 'requestAccessTokenWithAuthCode',
                              'requestAccessTokenWithSteam', 'requestAccessTokenWithOculus', 'refreshAccessToken',
                              'requestAccessTokenFinished', 'refreshAccessTokenFinished', 'refreshAccessTokenError'))
        methods += '\n' + block(source, 'bool AccountManager::setAccessTokens(')
        if 'void AccountManager::requestAccessTokenError(' in source:
            methods += '\n' + block(source, 'void AccountManager::requestAccessTokenError(')
            variant = ['-DOVERTE_ACCOUNT_HAS_ERROR_SLOT=1']
        else:
            variant = []
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Network'], text=True))
        moc = Path(subprocess.check_output(['pkg-config', '--variable=libexecdir', 'Qt6Core'], text=True).strip()) / 'moc'
        here = Path(__file__).parent
        with tempfile.TemporaryDirectory(prefix='overte-account-context-') as temporary:
            scratch = Path(temporary)
            (scratch / 'context.inc').write_text(methods)
            subprocess.run([str(moc), *variant, str(here / 'account-auth-context-test.cpp'),
                            '-o', str(scratch / 'context.moc')], check=True, timeout=15)
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), '-I', str(scratch),
                            str(here / 'account-auth-context-test.cpp'), '-o', str(binary), *variant, *flags],
                           check=True, timeout=30)
            subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary)], check=True, timeout=8)


if __name__ == '__main__':
    unittest.main()
