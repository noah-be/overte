#!/usr/bin/env python3
"""Compile Pico's actual common host selection, not the combined Phone/Gradle build."""
# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
COMMON = ROOT / 'android/common/tests/robolectric'


class CommonHostCompileTest(unittest.TestCase):
    def test_exact_pico_selection_with_released_common_boundary(self):
        source = (COMMON / 'build.gradle').read_text()
        main = source.split('    main {', 1)[1].split('    test {', 1)[0]
        selected = re.findall(r"include '(org/overte/pico/[^']+[.]java)'", main)
        self.assertTrue(selected)
        self.assertEqual(len(selected), len(set(selected)))
        self.assertIn("include 'org/overte/security/SafeDiagnostics.java'", main)
        shared = re.search(r"def sharedRedactionJava = file\('([^']+)'\)", source).group(1)
        self.assertEqual((COMMON / shared).resolve(), ROOT / 'security/redaction/java')
        java = ROOT / 'android/vr/pico/apps/picoInterface/src/main/java'
        boundary = COMMON / 'src/main/java/org/overte/pico'
        self.assertIn('getInstance() { return null; }', (boundary / 'PicoInterfaceActivity.java').read_text())
        sdk = Path(os.environ.get('ANDROID_SDK_ROOT', str(Path.home() / 'Android/Sdk')))
        with tempfile.TemporaryDirectory(prefix='pico-common-host-selection-') as temporary:
            subprocess.run(['javac', '--release', '17', '-cp', str(sdk / 'platforms/android-36/android.jar'),
                '-d', temporary, *[str(java / name) for name in selected],
                str(ROOT / 'security/redaction/java/org/overte/security/SafeDiagnostics.java'),
                str(boundary / 'PicoInterfaceActivity.java'), str(boundary / 'R.java')],
                check=True, timeout=30)


if __name__ == '__main__':
    unittest.main(verbosity=2)
