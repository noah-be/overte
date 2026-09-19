#!/usr/bin/env python3
"""Compile production Android primitives and exercise their real JVM crypto code."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
JAVA = ROOT / 'android/vr/pico/apps/picoInterface/src/main/java/org/overte/pico'
TESTS = Path(__file__).parent / 'java/org/overte/pico'


class NativeSecurityTest(unittest.TestCase):
    def test_production_crypto_and_android_minimum_api_compile(self):
        sdk = Path(os.environ.get('ANDROID_SDK_ROOT', str(Path.home() / 'Android/Sdk')))
        android_jar = sdk / 'platforms/android-26/android.jar'
        self.assertTrue(android_jar.is_file(), 'API 26 android.jar required for minimum-API check')
        with tempfile.TemporaryDirectory(prefix='pico-native-security-') as scratch:
            subprocess.run(['javac', '-encoding', 'UTF-8', '-d', scratch,
                            str(JAVA / 'ProtectedRecordCodec.java'),
                            str(TESTS / 'ProtectedRecordCodecTest.java')], check=True, timeout=30)
            subprocess.run(['java', '-cp', scratch, 'org.overte.pico.ProtectedRecordCodecTest'],
                           check=True, timeout=30)
            subprocess.run(['javac', '-encoding', 'UTF-8', '-cp', str(android_jar), '-d', scratch,
                            *[str(JAVA / name) for name in ('ProtectedRecordCodec.java',
                              'SecureAccountStore.java', 'RestartArguments.java',
                              'PicoRestartUrlPolicy.java')]],
                           check=True, timeout=30)


if __name__ == '__main__':
    unittest.main(verbosity=2)
