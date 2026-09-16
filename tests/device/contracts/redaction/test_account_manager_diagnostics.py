"""Actual AccountManager Qt expressions and three complete production methods."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class AccountDiagnostics(unittest.TestCase):
    def test_original_sinks_and_state_mutations(self):
        baseline = os.environ.get('OVERTE_ACCOUNT_DIAGNOSTICS_BASELINE')
        relative = 'libraries/networking/src/AccountManager.cpp'
        source = (subprocess.check_output(['git', '-C', str(ROOT), 'show', baseline + ':' + relative],
                  text=True) if baseline else (ROOT / relative).read_text())
        calls = re.findall(r'^\s*(q(?:CDebug|CWarning|Critical)\([^)]*\)\s*<<[^;]+;)', source, re.M)
        self.assertEqual(len(calls), 53)
        for call in calls:
            self.assertRegex(call, r'^q(?:CDebug|CWarning|Critical)\((?:networking)?\) << '
                             r'overte::security::diagnosticEvent\(overte::security::DiagnosticEvent::(?:Redacted|AuthReady)\);$')
        self.assertEqual(sum('DiagnosticEvent::AuthReady' in call for call in calls), 1)
        methods = []
        for name in ('setSessionID', 'publicKeyUploadFailed', 'handleKeypairGenerationError'):
            start = source.index('void AccountManager::' + name + '(')
            end = source.index('\n}', start) + 2
            methods.append(source[start:end])
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-account-diagnostics-') as temporary:
            scratch = Path(temporary)
            (scratch / 'sinks.inc').write_text('\n'.join(calls))
            (scratch / 'methods.inc').write_text('\n'.join(methods))
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), '-I', str(scratch),
                            str(Path(__file__).with_name('account-manager-diagnostics-test.cpp')),
                            '-o', str(binary), *flags], check=True, timeout=30)
            subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary)],
                           check=True, timeout=8)


if __name__ == '__main__':
    unittest.main()
