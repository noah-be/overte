"""Original direct token import and Application preference caller, real Qt."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest
from test_login_dialog_domain_receiver import block
ROOT = Path(__file__).resolve().parents[4]


class TokenImport(unittest.TestCase):
    def test_original_token_import_and_application_result(self):
        baseline = os.environ.get('OVERTE_TOKEN_IMPORT_BASELINE')
        def source(path):
            return (subprocess.check_output(['git', '-C', str(ROOT), 'show', baseline + ':' + path], text=True)
                    if baseline else (ROOT / path).read_text())
        account = source('libraries/networking/src/AccountManager.cpp')
        header = source('libraries/networking/src/AccountManager.h')
        return_type = re.search(r'\b(bool|void) setAccessTokens\(const QString& response\);', header).group(1)
        methods = block(account, return_type + ' AccountManager::setAccessTokens(')
        methods += '\n' + block(source('interface/src/Application.cpp'), 'void Application::forceLoginWithTokens(')
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Network'], text=True))
        moc = Path(subprocess.check_output(['pkg-config', '--variable=libexecdir', 'Qt6Core'], text=True).strip()) / 'moc'
        driver = Path(__file__).with_name('account-token-import-test.cpp')
        with tempfile.TemporaryDirectory(prefix='overte-token-import-') as temporary:
            scratch = Path(temporary)
            (scratch / 'token-import.inc').write_text(methods)
            (scratch / 'token-return.inc').write_text(return_type + '\n')
            subprocess.run([str(moc), str(driver), '-o', str(scratch / 'token-import.moc')], check=True, timeout=15)
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), '-I', str(scratch),
                            str(driver), '-o', str(binary), *flags], check=True, timeout=30)
            subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary)], check=True, timeout=8)


if __name__ == '__main__': unittest.main()
