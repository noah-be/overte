"""Execute original LoginDialog console sites using the real Qt JS console sink.

Only console expressions are extracted, not complete QML components or handlers.
Native loaders, fields, screenshots and server transport are outside this check.
"""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class LoginQmlDiagnostics(unittest.TestCase):
    def test_actual_console_sites_are_closed_and_do_not_emit_seeded_fields(self):
        directory = ROOT / 'interface/resources/qml/LoginDialog'
        baseline = os.environ.get('OVERTE_LOGIN_QML_BASELINE')
        statements = []
        for path in sorted(directory.rglob('*.qml')):
            source = (subprocess.check_output(
                ['git', '-C', str(ROOT), 'show', baseline + ':' + str(path.relative_to(ROOT))],
                text=True) if baseline else path.read_text())
            sites = re.findall(r'console\.(?:log|warn|error|debug|info)\s*\([^\n]*', source)
            for site in sites:
                self.assertRegex(site, r'^console\.(?:log|warn|error|debug|info)\("[^"\\]*"\);?\s*$',
                                 str(path.relative_to(ROOT)))
            statements.extend(sites)
        self.assertEqual(len(statements), 24, 'review changed production sink inventory')
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Qml'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-login-qml-diagnostics-') as temporary:
            scratch = Path(temporary)
            (scratch / 'sites.js').write_text(';\n'.join(statements))
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', str(Path(__file__).with_name(
                'login-qml-diagnostics-test.cpp')), '-o', str(binary), *flags],
                check=True, timeout=30)
            subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary),
                            str(scratch / 'sites.js')], check=True, timeout=8)


if __name__ == '__main__':
    unittest.main()
