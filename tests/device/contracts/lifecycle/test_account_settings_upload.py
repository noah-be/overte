"""Original settings PUT/completion methods with real Qt transport objects."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from test_login_dialog_domain_receiver import block

ROOT = Path(__file__).resolve().parents[4]


class SettingsUpload(unittest.TestCase):
    def test_original_header_and_production_methods_compile_together(self):
        source = (ROOT / 'libraries/networking/src/AccountManager.cpp').read_text()
        methods = block(source, 'static void observeAccountTokenDeadline(') + '\n'
        methods += block(source, 'void AccountManager::resetAccountSettings(') + '\n'
        methods += '\n'.join(block(source, 'void AccountManager::' + name + '(')
                             for name in ('postAccountSettings', 'postAccountSettingsFinished',
                                          'postAccountSettingsError', 'requestAccountSettings',
                                          'requestAccountSettingsFinished', 'requestAccountSettingsError',
                                          'setAccountInfo', 'setAccessTokenForCurrentAuthURL'))
        methods = 'static const int MAX_PULL_RETRIES = 3;\n' + methods
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', 'Qt6Core', 'Qt6Network'], text=True))
        includes = '\n'.join('#include "' + path + '"' for path in (
            'libraries/networking/src/AccountManager.h',
            'libraries/networking/src/NetworkLogging.h',
            'security/redaction/SafeDiagnostics.h'))
        includes += '\n#include <QtCore/QPointer>\n#include <QtCore/QJsonDocument>\n'
        with tempfile.TemporaryDirectory(prefix='overte-settings-header-') as temporary:
            unit = Path(temporary) / 'methods.cpp'
            unit.write_text(includes + methods)
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-fsyntax-only', '-I', str(ROOT),
                            '-I', str(ROOT / 'libraries/shared/src'),
                            '-I', str(ROOT / 'libraries/networking/src'),
                            *flags, str(unit),
                            str(ROOT / 'libraries/networking/src/AccountSettings.cpp')],
                           check=True, timeout=30)

    def test_acknowledgement_is_bound_to_the_sent_settings(self):
        source = (ROOT / 'libraries/networking/src/AccountManager.cpp').read_text()
        methods = block(source, 'static void observeAccountTokenDeadline(') + '\n'
        methods += block(source, 'void AccountManager::resetAccountSettings(') + '\n'
        methods += '\n'.join(block(source, 'void AccountManager::' + name + '(')
                            for name in ('postAccountSettings', 'postAccountSettingsFinished',
                                         'postAccountSettingsError', 'requestAccountSettings',
                                         'requestAccountSettingsFinished', 'requestAccountSettingsError'))
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Network'], text=True))
        moc = Path(subprocess.check_output(
            ['pkg-config', '--variable=libexecdir', 'Qt6Core'], text=True).strip()) / 'moc'
        driver = Path(__file__).with_name('account-settings-upload-test.cpp')
        with tempfile.TemporaryDirectory(prefix='overte-settings-upload-') as temporary:
            scratch = Path(temporary)
            (scratch / 'settings.inc').write_text(methods)
            subprocess.run([str(moc), str(driver), '-o', str(scratch / 'settings.moc')],
                           check=True, timeout=15)
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), '-I', str(scratch),
                            str(driver), '-o', str(binary), *flags], check=True, timeout=30)
            subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary)],
                           check=True, timeout=8)


if __name__ == '__main__':
    unittest.main()
