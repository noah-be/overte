#!/usr/bin/env python3
"""Original complete Button/CheckBox/RadioButton on real Qt Quick; OS is a fixture."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]


class UiButton(unittest.TestCase):
    def test_actual_button_cancellation_focus_and_keyboard(self):
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core", "Qt6Gui", "Qt6Qml", "Qt6Quick", "Qt6Test"], text=True))
        moc = pathlib.Path(subprocess.check_output(["pkg-config", "--variable=libexecdir", "Qt6Core"], text=True).strip()) / "moc"
        here = pathlib.Path(__file__).parent
        with tempfile.TemporaryDirectory(prefix="sh003-button-") as temporary:
            temporary = pathlib.Path(temporary)
            generated = temporary / "moc.cpp"
            subprocess.run([str(moc), str(here / "ui-button-boundary.h"), "-o", str(generated)], check=True, timeout=10)
            binary = temporary / "test"
            subprocess.run(["c++", "-std=c++17", "-fPIC", str(here / "ui-button-test.cpp"), str(generated),
                            "-o", str(binary), *flags], check=True, timeout=30)
            for control in ("Button", "CheckBox", "RadioButton"):
                for platform in ("android", "linux", "ios"):
                    with self.subTest(control=control, platform=platform):
                        subprocess.run(["unshare", "--user", "--map-root-user", "--net", str(binary),
                                        str(ROOT / ("interface/resources/qml/controlsUit/" + control + ".qml")), platform],
                                       env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"},
                                       check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
