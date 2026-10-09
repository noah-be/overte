"""Actual hidden-window Qt Quick accessibility, Unicode editing and teardown."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class PhoneAccessibilityTreeTests(unittest.TestCase):
    def run_driver(self, driver_name, arguments=()):
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core', 'Qt6Gui', 'Qt6Quick', 'Qt6Qml'], text=True))
        ui = ROOT / 'libraries/ui/src/ui'
        driver = Path(__file__).with_name(driver_name)
        with tempfile.TemporaryDirectory(prefix='overte-phone-accessibility-') as temporary:
            binary = Path(temporary) / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ui), str(driver),
                            str(ui / 'PhoneAccessibilityTree.cpp'), str(ui / 'PhoneTextInputFixture.cpp'), '-o', str(binary), *flags],
                           check=True, timeout=40)
            subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary), *arguments],
                           env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software'},
                           check=True, timeout=10)

    def test_real_qt_items_and_actions(self):
        self.run_driver('phone-accessibility-tree-test.cpp')

    def test_product_text_control_unicode_keys_submit_and_dismissal(self):
        self.run_driver('phone-text-input-test.cpp', [str(ROOT)])


if __name__ == '__main__':
    unittest.main()
