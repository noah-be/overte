#!/usr/bin/env python3
"""Run the Java URL policy used by production restart callers."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
JAVA = ROOT / 'android/vr/pico/apps/picoInterface/src/main/java/org/overte/pico'

class NativeUrlTest(unittest.TestCase):
    def test_native_policy(self):
        with tempfile.TemporaryDirectory(prefix='pico-native-url-') as scratch:
            subprocess.run(['javac', '-encoding', 'UTF-8', '-d', scratch,
                str(JAVA / 'PicoRestartUrlPolicy.java'),
                str(Path(__file__).parent / 'java/org/overte/pico/PicoRestartUrlPolicyTest.java')],
                check=True, timeout=30)
            subprocess.run(['java', '-cp', scratch, 'org.overte.pico.PicoRestartUrlPolicyTest'],
                check=True, timeout=30)

    def test_actual_restart_caller_checks_before_storage_and_after_consumption(self):
        source = (JAVA / 'RestartArguments.java').read_text()
        self.assertLess(source.index('PicoRestartUrlPolicy.arguments(arguments)'),
                        source.index('.write(SLOT, bytes)'))
        self.assertIn('PicoRestartUrlPolicy.arguments(\n                new String(bytes', source)
        self.assertIn('RestartArguments.store(activity, applicationArguments)',
                      (JAVA / 'PicoInterfaceActivity.java').read_text())
        self.assertIn('RestartArguments.consume(this)', (JAVA / 'RestartActivity.java').read_text())

if __name__ == '__main__':
    unittest.main(verbosity=2)
