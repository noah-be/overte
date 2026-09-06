#!/usr/bin/env python3
"""Real JVM/JNI transport and Shared coordinator; test backend is NOT Android Keystore evidence."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[5]
PICO = ROOT / 'android/vr/pico'
JAVA = PICO / 'apps/picoInterface/src/main/java/org/overte/pico'
HERE = Path(__file__).parent

class AccountJniTest(unittest.TestCase):
    def test_actual_startup_prepares_peer_and_cmake_builds_bridge_once(self):
        activity = (JAVA / 'PicoInterfaceActivity.java').read_text()
        self.assertLess(activity.index('prepareProtectedAccountStore(new PicoAccountStoreBridge(this))'),
                        activity.index('super.onCreate(savedInstanceState)'))
        cmake = (PICO / 'apps/picoInterface/CMakeLists.txt').read_text()
        self.assertEqual(cmake.count('security/PicoAccountStore.cpp'), 1)
        self.assertIn('target_sources(picoOpenXR PRIVATE', cmake)
        setup = (PICO / 'apps/picoInterface/overrides/Application_Setup.cpp').read_text()
        registration = 'AccountManager::installProtectedAccountStore(overte::pico::protectedAccountStore())'
        self.assertEqual(setup.count(registration), 1)
        self.assertLess(setup.index(registration), setup.index('DependencyManager::set<AccountManager>'))
        self.assertIn('qWarning("OVT_STORAGE_UNAVAILABLE")', setup)
        self.assertNotIn('ExceptionDescribe(', (PICO / 'apps/picoInterface/security/PicoAccountStore.cpp')
                         .read_text().replace('Never ExceptionDescribe():', 'Never describe:'))

    def test_production_transport_and_contract(self):
        sdk = Path(os.environ.get('ANDROID_SDK_ROOT', str(Path.home() / 'Android/Sdk')))
        jar = sdk / 'platforms/android-26/android.jar'
        jdk = Path(shutil.which('javac')).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='pico-px15-jni-') as scratch:
            def run(*args):
                result = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn('private fixture', result.stdout + result.stderr)
                print(result.stdout, end='')
            run('javac', '-cp', jar, '-d', scratch,
                JAVA / 'ProtectedRecordCodec.java', JAVA / 'SecureAccountStore.java',
                JAVA / 'PicoAccountStoreBridge.java', HERE / 'java/org/overte/pico/PicoAccountBridgeTest.java',
                HERE / 'java-stubs/android/security/keystore/UserNotAuthenticatedException.java')
            classpath = scratch + os.pathsep + str(jar)
            run('java', '-cp', classpath, 'org.overte.pico.PicoAccountBridgeTest')
            executable = Path(scratch) / 'jni-test'
            run('c++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-pthread',
                '-I' + str(jdk / 'include'), '-I' + str(jdk / 'include/linux'),
                HERE / 'native/account-jni-test.cpp', PICO / 'apps/picoInterface/security/PicoAccountStore.cpp',
                '-L' + str(jdk / 'lib/server'), '-Wl,-rpath,' + str(jdk / 'lib/server'), '-ljvm', '-o', executable)
            run(executable, classpath)
            coordinator = Path(scratch) / 'coordinator'
            run('c++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-pthread',
                ROOT / 'tests/device/contracts/secure-storage/coordinator-test.cpp', '-o', coordinator)
            run(coordinator)

if __name__ == '__main__':
    unittest.main(verbosity=2)
