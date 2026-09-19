#!/usr/bin/env python3
"""Exercise actual Pico sink wrappers and the published PX-16 canary corpus."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
APP = ROOT / 'android/vr/pico/apps/picoInterface'
JAVA = APP / 'src/main/java/org/overte/pico'
HERE = Path(__file__).parent

class DiagnosticsTest(unittest.TestCase):
    def test_sink_wrappers_and_shared_canaries(self):
        with tempfile.TemporaryDirectory(prefix='pico-px16-') as scratch:
            def run(*args):
                subprocess.run(list(map(str, args)), check=True, timeout=30)
            run('javac', '-d', scratch, ROOT / 'security/redaction/java/org/overte/security/SafeDiagnostics.java',
                ROOT / 'tests/device/contracts/redaction/SanitizerTest.java', JAVA / 'RedactingDiagnostics.java',
                HERE / 'java-stubs/android/util/Log.java', HERE / 'java/org/overte/pico/PicoDiagnosticsTest.java')
            run('java', '-cp', scratch, 'SanitizerTest')
            run('java', '-cp', scratch, 'org.overte.pico.PicoDiagnosticsTest')
            for source in (ROOT / 'tests/device/contracts/redaction/sanitizer-test.cpp', HERE / 'native/diagnostics-test.cpp'):
                executable = Path(scratch) / source.stem
                run('c++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-I' + str(HERE / 'native-stubs'),
                    source, '-o', executable)
                run(executable)

    def test_actual_callers_cannot_bypass_wrappers(self):
        for source in JAVA.glob('*.java'):
            text = source.read_text()
            if source.name != 'RedactingDiagnostics.java':
                self.assertNotRegex(text, r'\bLog\.[a-z]+\(', source.name)
            self.assertNotRegex(text, r'printStackTrace\(|System\.(out|err)', source.name)
            for argument in re.findall(r'RedactingDiagnostics\.[iew]\((.*?)\);', text, re.S):
                self.assertRegex(argument, r'^Event\.[A-Z_]+$', source.name)
        for relative in ('src/PicoWebViewItem.cpp', 'src/main/cpp/OpenXRLoader.cpp',
                         'openxr/e2e_input/E2eInputProtocol.cpp', 'openxr/e2e_input/XrApiLayer.cpp'):
            text = (APP / relative).read_text()
            self.assertNotIn('__android_log_', text)
            self.assertNotIn('ExceptionDescribe', text)
            self.assertIn('RedactingDiagnostics.h', text)
        self.assertIn("java.srcDir '../../../../../security/redaction/java'", (APP / 'build.gradle').read_text())

if __name__ == '__main__':
    unittest.main(verbosity=2)
