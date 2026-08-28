#!/usr/bin/env python3
"""Static contract for the shared QML controls used by physical iOS E2E."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    action_bar = (
        ROOT / "scripts/system/+android_phoneInterface/mobileActionBar.js"
    ).read_text(encoding="utf-8")
    tablet_home = (
        ROOT / "interface/resources/qml/hifi/tablet/TabletHome.qml"
    ).read_text(encoding="utf-8")
    button_qml = (
        ROOT / "interface/resources/qml/hifi/+android_interface/button.qml"
    ).read_text(encoding="utf-8")
    native_bridge = (
        ROOT / "interface/src/IOSTouchUiMetrics.mm"
    ).read_text(encoding="utf-8")
    interface_cmake = (
        ROOT / "interface/CMakeLists.txt"
    ).read_text(encoding="utf-8")
    application = (
        ROOT / "interface/src/Application_Graphics.cpp"
    ).read_text(encoding="utf-8")

    assert action_bar.count('objectName: "OverteTabletOpen"') == 1
    assert tablet_home.count('objectName: "OverteTabletClose"') == 1
    assert "tabletButton = addButton(navigationBar" in action_bar
    assert "onClicked: tabletProxy.hideAndroidTablet()" in tablet_home
    assert "Accessible.role: Accessible.Button" in button_qml
    assert "Accessible.id: objectName" in button_qml
    assert "Accessible.name: text" in button_qml
    assert "Accessible.onPressAction: clicked()" in button_qml
    assert "activeFocusOnTab: true" in button_qml
    assert "Accessible.id: objectName" in tablet_home
    assert "Accessible.onPressAction: tabletProxy.hideAndroidTablet()" in tablet_home
    assert native_bridge.count('@"OverteTabletOpen"') == 1
    assert native_bridge.count('@"OverteTabletClose"') == 1
    assert "OverteIOSAccessibilityElement : UIAccessibilityElement" in native_bridge
    assert "UIAccessibilityTraitButton" in native_bridge
    assert "guardedTablet->showAndroidTablet(width, height)" in native_bridge
    assert "guardedTablet->hideAndroidTablet()" in native_bridge
    assert "OverteIOSAccessibilityOverlay : UIView" in native_bridge
    assert "pointInside:(CGPoint)point withEvent:(UIEvent*)event" in native_bridge
    assert "return NO;" in native_bridge
    assert re.search(
        r'set_source_files_properties\(\s*'
        r'"\$\{CMAKE_CURRENT_SOURCE_DIR\}/src/IOSTouchUiMetrics[.]mm"\s*'
        r'PROPERTIES\s+COMPILE_OPTIONS\s+"-fobjc-arc"\s*\)',
        interface_cmake,
    )
    assert "updateIOSTabletAccessibilityControls(systemTablet" in application
    assert "&TabletProxy::tabletShownChanged" in application
    print("PASS stable iOS tablet accessibility identifiers")


if __name__ == "__main__":
    main()
