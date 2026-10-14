"""Complete original constructor and real Qt/QML domain completion receivers."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[4]


def block(source, marker):
    start = source.index(marker)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class DomainReceiver(unittest.TestCase):
    def test_original_constructor_and_qml_terminal_handlers(self):
        baseline = os.environ.get('OVERTE_LOGIN_RECEIVER_BASELINE')
        source = (subprocess.check_output(['git', '-C', str(ROOT), 'show',
                  baseline + ':interface/src/ui/LoginDialog.cpp'], text=True)
                  if baseline else (ROOT / 'interface/src/ui/LoginDialog.cpp').read_text())
        qml_relative = 'interface/resources/qml/LoginDialog/LoggingInBody.qml'
        qml_baseline = os.environ.get('OVERTE_LOGIN_QML_BASELINE')
        qml = (subprocess.check_output(['git', '-C', str(ROOT), 'show',
            qml_baseline + ':' + qml_relative], text=True) if qml_baseline else (ROOT / qml_relative).read_text())
        getter_source = (ROOT / 'interface/src/ui/LoginDialog.cpp').read_text()
        self.assertIn('Connections {\n        target: loginDialog', qml)
        functions = '\n'.join(block(qml, 'function ' + name + '(') for name in
                              ('onHandleLoginCompleted', 'onHandleLoginFailed', 'onHandleDomainLoginFailed'))
        success = block(qml, 'function loadingSuccess(')
        qt = os.environ.get('OVERTE_LOGIN_TEST_QT', 'Qt6')
        self.assertIn(qt, ('Qt5', 'Qt6'))
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', qt + 'Core', qt + 'Qml', qt + 'Network'], text=True))
        if qt == 'Qt5' and os.environ.get('PKG_CONFIG_SYSROOT_DIR'):
            library = subprocess.check_output(
                ['pkg-config', '--variable=libdir', qt + 'Core'], text=True).strip()
            flags = ['-L' + library, *flags]
        tool_variable = 'libexecdir' if qt == 'Qt6' else 'host_bins'
        moc = pathlib.Path(subprocess.check_output(
            ['pkg-config', '--variable=' + tool_variable, qt + 'Core'], text=True).strip()) / 'moc'
        if not moc.is_file() and os.environ.get('PKG_CONFIG_SYSROOT_DIR'):
            moc = pathlib.Path(os.environ['PKG_CONFIG_SYSROOT_DIR']) / str(moc).lstrip('/')
        here = pathlib.Path(__file__).parent
        variant = os.environ.get('OVERTE_LOGIN_VARIANT', 'main')
        self.assertIn(variant, ('main', 'apple'))
        with tempfile.TemporaryDirectory(prefix='overte-domain-receiver-') as temporary:
            directory = pathlib.Path(temporary)
            (directory / 'constructor.inc').write_text(block(source, 'LoginDialog::LoginDialog(') + '\n' +
                                                      block(source, 'void LoginDialog::loginDomain(') + '\n' +
                                                      block(getter_source, 'bool LoginDialog::getAccountLoginTransportRejected('))
            account_header = (ROOT / 'libraries/networking/src/AccountManager.h').read_text()
            (directory / 'account-transport-accessor.inc').write_text(
                block(account_header, '    bool lastLoginTransportRejected('))
            fixture = (here / 'login-dialog-domain-receiver.qml').read_text()
            (directory / 'receiver.qml').write_text(fixture.replace('/* ORIGINAL_HANDLERS */', functions)
                                                   .replace('/* ORIGINAL_SUCCESS */', success))
            subprocess.run([str(moc), str(here / 'login-dialog-domain-receiver-test.cpp'),
                            '-o', str(directory / 'receiver.moc')], check=True, timeout=15)
            for platform in ('pico', 'phone', 'desktop', 'ios', 'legacy-android'):
                with self.subTest(platform=platform):
                    binary = directory / platform
                    subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), '-I', str(directory),
                                    '-DTEST_ANDROID=' + str(int(platform in ('pico', 'phone', 'legacy-android'))),
                                    '-DTEST_PHONE=' + str(int(platform == 'phone')),
                                    '-DTEST_PICO=' + str(int(platform == 'pico')),
                                    '-DTEST_IOS=' + str(int(platform == 'ios')),
                                    '-DTEST_EXPECT_PENDING=' + str(int(platform == 'phone' or
                                                                   (platform == 'ios' and variant == 'apple'))),
                                    str(here / 'login-dialog-domain-receiver-test.cpp'),
                                    '-o', str(binary), *flags], check=True, timeout=30)
                    subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary),
                                    str(directory / 'receiver.qml')], check=True, timeout=8)


if __name__ == '__main__':
    unittest.main()
