"""Real Account persistence failure -> token import -> Application caller."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from test_login_dialog_domain_receiver import block

ROOT = Path(__file__).resolve().parents[4]


class PersistenceContext(unittest.TestCase):
    def test_original_persistence_failure_closes_token_completion(self):
        baseline = os.environ.get('OVERTE_PERSISTENCE_BASELINE')
        def source(path):
            return (subprocess.check_output(['git', '-C', str(ROOT), 'show', baseline + ':' + path], text=True)
                    if baseline else (ROOT / path).read_text())
        account = source('libraries/networking/src/AccountManager.cpp')
        methods = block(account, 'void AccountManager::persistAccountToFile(')
        methods += '\n' + block(account, 'bool AccountManager::setAccessTokens(')
        methods += '\n' + block(source('interface/src/Application.cpp'), 'void Application::forceLoginWithTokens(')
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Network'], text=True))
        moc = Path(subprocess.check_output(['pkg-config', '--variable=libexecdir', 'Qt6Core'], text=True).strip()) / 'moc'
        driver = Path(__file__).with_name('account-persistence-context-test.cpp')
        with tempfile.TemporaryDirectory(prefix='overte-persistence-context-') as temporary:
            scratch = Path(temporary)
            (scratch / 'persistence.inc').write_text(methods)
            subprocess.run([str(moc), str(driver), '-o', str(scratch / 'persistence.moc')], check=True, timeout=15)
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), '-I', str(scratch),
                            str(driver), '-o', str(binary), *flags], check=True, timeout=30)
            subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary)], check=True, timeout=8)


if __name__ == '__main__':
    unittest.main()
