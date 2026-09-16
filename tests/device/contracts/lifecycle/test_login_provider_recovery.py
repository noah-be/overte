"""Complete original provider recovery handlers on real Qt JS, loader boundary."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from test_login_dialog_domain_receiver import block

ROOT = Path(__file__).resolve().parents[4]


class ProviderRecovery(unittest.TestCase):
    def test_original_handlers_do_not_forward_provider_payload(self):
        relative = 'interface/resources/qml/LoginDialog/LoggingInBody.qml'
        baseline = os.environ.get('OVERTE_PROVIDER_RECOVERY_BASELINE')
        source = (subprocess.check_output(['git', '-C', str(ROOT), 'show',
                  baseline + ':' + relative], text=True) if baseline else (ROOT / relative).read_text())
        handlers = '\n'.join(block(source, 'function ' + name + '(') for name in
                             ('onHandleCreateFailed', 'onHandleLinkFailed'))
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Qml'], text=True))
        here = Path(__file__).parent
        with tempfile.TemporaryDirectory(prefix='overte-provider-recovery-') as temporary:
            scratch = Path(temporary)
            fixture = (here / 'login-provider-recovery.js').read_text()
            (scratch / 'handlers.js').write_text(fixture.replace('/* ORIGINAL_HANDLERS */', handlers))
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', str(here / 'login-provider-recovery-test.cpp'),
                            '-o', str(binary), *flags], check=True, timeout=30)
            subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary),
                            str(scratch / 'handlers.js')], check=True, timeout=8)


if __name__ == '__main__':
    unittest.main()
