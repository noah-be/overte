#!/usr/bin/env python3
"""Compile every production Pico Java caller using SDK 36 and explicit dependency stubs.

This is a focused javac check, not a Gradle build or Android execution.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
JAVA = ROOT / 'android/vr/pico/apps/picoInterface/src/main/java/org/overte/pico'
HERE = Path(__file__).parent

class ProductionJavaCompileTest(unittest.TestCase):
    def test_all_production_pico_java_sources_compile(self):
        sdk = Path(os.environ.get('ANDROID_SDK_ROOT', str(Path.home() / 'Android/Sdk')))
        stubs = [HERE / 'java-stubs' / name for name in (
            'org/qtproject/qt5/android/bindings/QtActivity.java',
            'io/highfidelity/utils/HifiUtils.java', 'org/overte/pico/R.java')]
        with tempfile.TemporaryDirectory(prefix='pico-production-javac-') as scratch:
            subprocess.run(['javac', '-encoding', 'UTF-8', '-cp',
                str(sdk / 'platforms/android-36/android.jar'), '-d', scratch,
                *map(str, sorted(JAVA.glob('*.java'))), *map(str, stubs),
                str(ROOT / 'security/redaction/java/org/overte/security/SafeDiagnostics.java')],
                check=True, timeout=60)

if __name__ == '__main__':
    unittest.main(verbosity=2)
