#!/usr/bin/env python3
"""Static contract for the shared QML controls used by physical iOS E2E."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class IOSAccessibilityIdentifierTest(unittest.TestCase):
    def test_shared_tablet_controls_expose_stable_identifiers(self):
        action_bar = (ROOT / "scripts/system/+android_phoneInterface/mobileActionBar.js").read_text(
            encoding="utf-8")
        tablet_home = (ROOT / "interface/resources/qml/hifi/tablet/TabletHome.qml").read_text(
            encoding="utf-8")
        button_qml = (ROOT / "interface/resources/qml/hifi/+android_interface/button.qml").read_text(
            encoding="utf-8")

        self.assertEqual(1, action_bar.count('objectName: "OverteTabletOpen"'))
        self.assertEqual(1, tablet_home.count('objectName: "OverteTabletClose"'))
        self.assertIn("tabletButton = addButton(navigationBar", action_bar)
        self.assertIn("onClicked: tabletProxy.hideAndroidTablet()", tablet_home)
        self.assertIn("Accessible.role: Accessible.Button", button_qml)
        self.assertIn("Accessible.id: objectName", button_qml)
        self.assertIn("Accessible.name: text", button_qml)
        self.assertIn("Accessible.onPressAction: clicked()", button_qml)
        self.assertIn("activeFocusOnTab: true", button_qml)
        self.assertIn('objectName: "OverteTabletClose"', tablet_home)
        self.assertIn("Accessible.id: objectName", tablet_home)
        self.assertIn("Accessible.onPressAction: tabletProxy.hideAndroidTablet()",
                      tablet_home)


if __name__ == "__main__":
    unittest.main()
