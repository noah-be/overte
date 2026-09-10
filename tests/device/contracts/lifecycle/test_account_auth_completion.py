"""Complete actual AccountManager finished handler on real Qt network signals."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from test_login_dialog_domain_receiver import block

ROOT = Path(__file__).resolve().parents[4]


class AccountCompletion(unittest.TestCase):
    def test_original_handler_terminal_failure_success_and_cleanup(self):
        baseline = os.environ.get('OVERTE_ACCOUNT_COMPLETION_BASELINE')
        relative = 'libraries/networking/src/AccountManager.cpp'
        source = (subprocess.check_output(['git', '-C', str(ROOT), 'show', baseline + ':' + relative],
                  text=True) if baseline else (ROOT / relative).read_text())
        method = block(source, 'void AccountManager::requestAccessTokenFinished(')
        refresh_baseline = os.environ.get('OVERTE_ACCOUNT_REFRESH_BASELINE')
        refresh_source = (subprocess.check_output(['git', '-C', str(ROOT), 'show',
                          refresh_baseline + ':' + relative], text=True)
                          if refresh_baseline else source)
        method += '\n' + block(refresh_source, 'void AccountManager::refreshAccessTokenFinished(')
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Network'], text=True))
        moc = Path(subprocess.check_output(['pkg-config', '--variable=libexecdir', 'Qt6Core'], text=True).strip()) / 'moc'
        here = Path(__file__).parent
        with tempfile.TemporaryDirectory(prefix='overte-account-completion-') as temporary:
            scratch = Path(temporary)
            (scratch / 'completion.inc').write_text(method)
            subprocess.run([str(moc), str(here / 'account-auth-completion-test.cpp'),
                            '-o', str(scratch / 'completion.moc')], check=True, timeout=15)
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), '-I', str(scratch),
                            str(here / 'account-auth-completion-test.cpp'), '-o', str(binary), *flags],
                           check=True, timeout=30)
            subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary)],
                           check=True, timeout=8)


if __name__ == '__main__':
    unittest.main()
