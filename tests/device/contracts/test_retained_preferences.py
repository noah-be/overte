#!/usr/bin/env python3
"""Real Qt Core/QML/Quick check of retained preference construction/persistence."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class RetainedPreferences(unittest.TestCase):
    def test_real_registry_and_original_qml_on_all_profiles(self):
        flags = shlex.split(subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "Qt6Core", "Qt6Gui", "Qt6Qml", "Qt6Quick"], text=True))
        libexec = subprocess.check_output(
            ["pkg-config", "--variable=libexecdir", "Qt6Core"], text=True).strip()
        header = ROOT / "libraries/shared/src/Preferences.h"
        source = ROOT / "libraries/shared/src/Preferences.cpp"
        driver = Path(__file__).with_name("retained-preferences-test.cpp")
        qml = ROOT / "interface/resources/qml"
        with tempfile.TemporaryDirectory(prefix="sh003-retained-") as scratch:
            scratch = Path(scratch)
            moc = scratch / "moc_preferences.cpp"
            subprocess.run([str(Path(libexec) / "moc"), str(header), "-o", str(moc)], check=True, timeout=20)
            stacks = {
                "desktop": [],
                "phone": ["-DSH003_TEST_ANDROID", '-DHIFI_ANDROID_APP="phoneInterface"'],
                "pico": ["-DSH003_TEST_ANDROID", '-DHIFI_ANDROID_APP="picoInterface"'],
                "ios": ["-DSH003_TEST_IOS"],
                "unknown": ["-DSH003_TEST_ANDROID", '-DHIFI_ANDROID_APP="unknown"'],
                "mixed": ["-DSH003_TEST_ANDROID", "-DSH003_TEST_IOS", '-DHIFI_ANDROID_APP="phoneInterface"'],
            }
            for name, defines in stacks.items():
                with self.subTest(profile=name):
                    binary = scratch / name
                    compilation = subprocess.run(["c++", "-std=c++17", "-fPIC", "-include",
                                    str(driver.with_name("retained-preferences-host-platform.h")),
                                    *defines, str(driver), str(source),
                                    str(moc), "-o", str(binary), *flags],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=45)
                    self.assertEqual(compilation.returncode, 0, compilation.stdout[-8000:])
                    subprocess.run([str(binary), str(qml / "dialogs/preferences"),
                                    str(qml / "hifi/tablet/tabletWindows/preferences")],
                                   env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"},
                                   check=True, timeout=15)


if __name__ == "__main__":
    unittest.main()
