"""Qt 5 short Settings clicks: real original failure and repaired navigation."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]

class PhoneSettingsClick(unittest.TestCase):
    def test_short_click_survives_the_native_parented_load(self):
        env = {**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software'}
        sysroot = os.environ.get('OVERTE_TEST_QT5_SYSROOT')
        moc = shutil.which('moc')
        if sysroot:
            sysroot = Path(sysroot).resolve()
            env.update(PKG_CONFIG_LIBDIR=str(sysroot / 'usr/lib64/pkgconfig'),
                       PKG_CONFIG_SYSROOT_DIR=str(sysroot),
                       LD_LIBRARY_PATH=str(sysroot / 'usr/lib64'),
                       LIBRARY_PATH=str(sysroot / 'usr/lib64'),
                       QML2_IMPORT_PATH=str(sysroot / 'usr/lib64/qt5/qml'),
                       QT_PLUGIN_PATH=str(sysroot / 'usr/lib64/qt5/plugins'))
            moc = str(sysroot / 'usr/lib64/qt5/bin/moc')
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt5Core', 'Qt5Gui', 'Qt5Qml', 'Qt5Quick', 'Qt5Test'],
            env=env, text=True))
        with tempfile.TemporaryDirectory(prefix='overte-settings-click-') as scratch:
            scratch = Path(scratch)
            driver = Path(__file__).with_name('phone-settings-click-test.cpp')
            subprocess.run([moc, str(driver), '-o', str(scratch / 'phone-settings-click-test.moc')],
                           env=env, check=True, timeout=20)
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(scratch), str(driver),
                            '-o', str(binary), *flags], env=env, check=True, timeout=40)
            original = scratch / 'settings'
            shutil.copytree(ROOT / 'scripts/system/settings', original)
            container = original / 'qml/SettingCenterContainer.qml'
            source = container.read_text()
            self.assertEqual(1, source.count('root.contentItem.pressDelay = 0'))
            container.write_text(source.replace('root.contentItem.pressDelay = 0',
                                                'root.contentItem.pressDelay = touchMetrics.pressDelay'))
            for page, expected in [(original / 'Settings.qml', 4),
                                   (ROOT / 'scripts/system/settings/Settings.qml', 0)]:
                with self.subTest(page='original' if expected else 'fixed'):
                    result = subprocess.run(['unshare', '--user', '--map-root-user', '--net',
                        str(binary), str(ROOT), str(page), 'short'], env=env,
                        capture_output=True, text=True, timeout=10)
                    self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
            copied_qml = scratch / 'qml'
            shutil.copytree(ROOT / 'interface/resources/qml', copied_qml)
            navigation = copied_qml / 'hifi/tablet/TabletNavigation.qml'
            source = navigation.read_text()
            self.assertEqual(1, source.count('fontSize: Math.round(16 * metrics.textScale)'))
            navigation.write_text(source.replace('fontSize: Math.round(16 * metrics.textScale)',
                                                 'font.pixelSize: Math.round(16 * metrics.textScale)'))
            for page, expected in [(navigation, 9),
                    (ROOT / 'interface/resources/qml/hifi/tablet/TabletNavigation.qml', 0)]:
                with self.subTest(navigation='original' if expected else 'fixed'):
                    result = subprocess.run(['unshare', '--user', '--map-root-user', '--net',
                        str(binary), str(ROOT), str(page), 'navigation'], env=env,
                        capture_output=True, text=True, timeout=10)
                    self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
            original_dialog = copied_qml / 'hifi/tablet/tabletWindows'
            dialog = original_dialog / 'TabletPreferencesDialog.qml'
            source = dialog.read_text()
            self.assertEqual(1, source.count('objectName: "GeneralPreferencesCancel"'))
            dialog.write_text(source.replace('objectName: "GeneralPreferencesCancel"',
                                             'objectName: "nav.back"'))
            for page, expected in [(dialog, 7),
                    (ROOT / 'interface/resources/qml/hifi/tablet/tabletWindows/TabletPreferencesDialog.qml', 0)]:
                with self.subTest(preferences='original' if expected else 'fixed'):
                    result = subprocess.run(['unshare', '--user', '--map-root-user', '--net',
                        str(binary), str(ROOT), str(page), 'preferences'], env=env,
                        capture_output=True, text=True, timeout=10)
                    self.assertEqual(expected, result.returncode, result.stdout + result.stderr)

if __name__ == '__main__':
    unittest.main()
