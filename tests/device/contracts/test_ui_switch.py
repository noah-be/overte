#!/usr/bin/env python3
"""Actual Audio mute Switch caller and complete Shared Switch on real Qt Quick."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest
from test_tablet_preferences_actions import block

ROOT = pathlib.Path(__file__).resolve().parents[3]


class UiSwitch(unittest.TestCase):
    def test_original_audio_label_keyboard_and_focus(self):
        qml = ROOT / "interface/resources/qml"
        source = (qml / "hifi/audio/Audio.qml").read_text()
        start = source.rindex("HifiControlsUit.Switch {", 0, source.index("id: muteMic;"))
        caller, _ = block(source, start)
        self.assertIn("AudioScriptingInterface.mutedDesktop = checked;", caller)
        self.assertIn("AudioScriptingInterface.mutedHMD = checked;", caller)
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core", "Qt6Gui", "Qt6Qml", "Qt6Quick", "Qt6Test"], text=True))
        with tempfile.TemporaryDirectory(prefix="sh003-switch-") as temporary:
            temporary = pathlib.Path(temporary)
            fixture = '''import QtQuick 2.7
import "CONTROLS" as HifiControlsUit
Item { id: root; width: 600; height: 180
 property int switchHeight: 40; property int switchWidth: 70
 property alias control: muteMic
 property alias mode: bar.currentIndex
 property bool muted: bar.currentIndex === 0 ? AudioScriptingInterface.mutedDesktop : AudioScriptingInterface.mutedHMD
 QtObject { id: bar; property int currentIndex: 0 }
 QtObject { id: touchConfiguration; property real textScale: 1 }
 CALLER
}'''.replace("CONTROLS", (qml / "controlsUit").as_uri()).replace("CALLER", caller)
            (temporary / "fixture.qml").write_text(fixture)
            binary = temporary / "test"
            subprocess.run(["c++", "-std=c++17", "-fPIC", str(pathlib.Path(__file__).with_name("ui-switch-test.cpp")),
                            "-o", str(binary), *flags], check=True, timeout=30)
            subprocess.run(["unshare", "--user", "--map-root-user", "--net", str(binary), str(temporary / "fixture.qml")],
                           env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"},
                           check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
