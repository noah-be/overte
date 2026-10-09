"""Actual Qt 5 accessibility cache and temporary-application ownership regressions."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class PhoneNativeStartup(unittest.TestCase):
    def compile_and_run(self, driver, modules, cases, qt5=False):
        env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software'}
        if qt5 and os.environ.get('OVERTE_TEST_QT5_SYSROOT'):
            sysroot = Path(os.environ['OVERTE_TEST_QT5_SYSROOT']).resolve()
            env.update({
                'PKG_CONFIG_LIBDIR': str(sysroot / 'usr/lib64/pkgconfig'),
                'PKG_CONFIG_SYSROOT_DIR': str(sysroot),
                'LD_LIBRARY_PATH': str(sysroot / 'usr/lib64'),
                'LIBRARY_PATH': str(sysroot / 'usr/lib64'),
                'QML2_IMPORT_PATH': str(sysroot / 'usr/lib64/qt5/qml'),
                'QT_PLUGIN_PATH': str(sysroot / 'usr/lib64/qt5/plugins'),
            })
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', *modules], env=env, text=True))
        with tempfile.TemporaryDirectory(prefix='overte-phone-native-startup-') as directory:
            executable = Path(directory) / 'test'
            subprocess.run([
                'c++', '-std=c++17', '-fPIC', '-DANDROID_APP_PHONE_INTERFACE',
                '-I', str(ROOT / 'libraries/qml/src/qml'),
                '-I', str(ROOT / 'android/phone/apps/phoneInterface/src'),
                str(Path(__file__).with_name(driver)), '-o', str(executable), *flags,
            ], check=True, env=env, timeout=40)
            for arguments, succeeds in cases:
                with self.subTest(arguments=arguments):
                    result = subprocess.run([
                        'unshare', '--user', '--map-root-user', '--net',
                        str(executable), *arguments,
                    ], capture_output=True, text=True, env=env, timeout=10)
                    if succeeds:
                        self.assertEqual(result.returncode, 0, result.stderr)
                    else:
                        # The original must reach the precise metadata failure.
                        self.assertEqual(result.returncode, 4, result.stderr)

    def test_real_qt5_early_lookup_and_original_negative(self):
        self.compile_and_run('phone-quick-startup-test.cpp',
                             ['Qt5Core', 'Qt5Gui', 'Qt5Qml', 'Qt5Quick'],
                             [(['original'], False), (['fixed'], True)], qt5=True)

    def test_real_temporary_parser_cannot_own_native_delivery(self):
        self.compile_and_run('phone-application-owner-test.cpp', ['Qt6Core', 'Qt6Gui'],
                             [([], True)])


if __name__ == '__main__':
    unittest.main()
