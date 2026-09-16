#!/usr/bin/env python3
"""Original derived buttons and full action functions on the actual Shared Button."""
import os
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]


def ui_variant():
    variant = os.environ.get("OVERTE_UI_VARIANT", "main")
    if variant not in ("main", "phone", "apple"):
        raise ValueError("OVERTE_UI_VARIANT must be main, phone or apple")
    return variant


def block(source, offset):
    start = source.index("{", offset)
    depth = 1
    for end in range(start + 1, len(source)):
        depth += (source[end] == "{") - (source[end] == "}")
        if depth == 0:
            return source[offset:end + 1], end + 1
    raise AssertionError("unclosed original QML block")


class TabletPreferenceActions(unittest.TestCase):
    def test_actual_derived_handlers_and_routes(self):
        variant = ui_variant()
        qml = ROOT / "interface/resources/qml"
        original = (qml / "hifi/tablet/tabletWindows/TabletPreferencesDialog.qml").read_text()
        self.assertNotIn("PICO_TABLET_PREFERENCES_", original)
        methods = original[original.index("    function saveAll() {"):original.index("    Rectangle {")]
        buttons = []
        offset = 0
        while "HifiControls.Button {" in original[offset:]:
            offset = original.index("HifiControls.Button {", offset)
            body, offset = block(original, offset)
            buttons.append(body)
        self.assertEqual(len(buttons), 2)
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core", "Qt6Gui", "Qt6Qml", "Qt6Quick", "Qt6Test"], text=True))
        here = pathlib.Path(__file__).parent
        with tempfile.TemporaryDirectory(prefix="sh003-tablet-actions-") as temporary:
            temporary = pathlib.Path(temporary)
            controls = temporary / "controlsUit"
            controls.mkdir()
            for name in ("Button.qml", "TouchUiMetrics.qml", "TouchUiProfile.qml", "TouchUiProfileBase.qml"):
                text = (qml / "controlsUit" / name).read_text()
                (controls / name).write_text(text.replace("Qt.platform.os", "testPlatformOS"))
            (temporary / "stylesUit").symlink_to(qml / "stylesUit", target_is_directory=True)
            fixture = '''import QtQuick 2.7
import "controlsUit" as HifiControls
import "stylesUit"
Item {
 id: harness; width: 600; height: 240
 property int saves: 0; property int restores: 0
 property int homes: 0; property int previous: 0; property int pops: 0; property int scripts: 0
 property string lastMessage: ""
 property bool hmdActive: false
 property alias previousFlag: dialog.gotoPreviousApp
 property alias scriptFlag: dialog.gotoPreviousAppFromScript
 property alias keyboardRaised: keyboard.raised
 property alias dialogItem: dialog
 property alias navigationItem: navigation
 function sendToScript(message) { scripts++; lastMessage = typeof message === "string" ? message : message.type; }
 QtObject { id: section; function saveAll() { harness.saves++; } function restoreAll() { harness.restores++; } }
 QtObject { id: navigation
   function gotoHomeScreen() { harness.homes++; }
   function returnToPreviousApp() { harness.previous++; }
   function popFromStack() { harness.pops++; }
 }
 Item {
  id: dialog; width: 600; height: 240
  property var sections: [section]
  property var showCategories: ["category-private-canary"]
  property bool gotoPreviousApp: false
  property bool gotoPreviousAppFromScript: false
  property var tablet: navigation
  HifiConstants { id: hifi }
  QtObject { id: keyboard; property bool raised: true }
  QtObject { id: preferencesLayout; property bool compactFooter: false }
  METHODS
  Row { x: 20; y: 20; spacing: 20; BUTTONS }
 }
}'''
            # Actual Tablet.getTablet/HMD are supplied as runtime context aliases
            # by the C++ harness; all four original action bodies remain intact.
            fixture = fixture.replace("METHODS", methods).replace("BUTTONS", "\n".join(buttons))
            (temporary / "fixture.qml").write_text(fixture.replace("Qt.platform.os", "testPlatformOS"))
            binary = temporary / "test"
            subprocess.run(["c++", "-std=c++17", "-fPIC", str(here / "tablet-preferences-actions-test.cpp"),
                            "-o", str(binary), *flags], check=True, timeout=30)
            subprocess.run(["unshare", "--user", "--map-root-user", "--net", str(binary), str(temporary / "fixture.qml"), variant],
                           env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"},
                           check=True, timeout=20)


if __name__ == "__main__":
    unittest.main()
