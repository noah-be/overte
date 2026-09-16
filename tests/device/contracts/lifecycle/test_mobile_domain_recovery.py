"""Original selected Phone/iOS terminal receiver, real Qt/QML Connections."""
import pathlib
import shlex
import subprocess
import tempfile
import unittest
from test_login_dialog_domain_receiver import block

ROOT = pathlib.Path(__file__).resolve().parents[4]


class MobileRecovery(unittest.TestCase):
    def test_selected_original_receiver_and_waiting_state(self):
        source = (ROOT / 'interface/resources/qml/LoginDialog/+android_phoneInterface/LinkAccountBody.qml').read_text()
        self.assertIn('Connections {\n        target: loginDialog', source)
        handler = block(source, 'function onHandleDomainLoginFailed(')
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Qml'], text=True))
        here = pathlib.Path(__file__).parent
        with tempfile.TemporaryDirectory(prefix='overte-mobile-domain-recovery-') as temporary:
            directory = pathlib.Path(temporary)
            fixture = (here / 'mobile-domain-recovery.qml').read_text()
            (directory / 'receiver.qml').write_text(fixture.replace('/* ORIGINAL_HANDLER */', handler))
            binary = directory / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', str(here / 'mobile-domain-recovery-test.cpp'),
                            '-o', str(binary), *flags], check=True, timeout=30)
            subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary),
                            str(directory / 'receiver.qml')], check=True, timeout=8)


if __name__ == '__main__':
    unittest.main()
