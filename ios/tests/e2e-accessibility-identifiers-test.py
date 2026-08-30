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
    tablet_proxy_header = (
        ROOT / "libraries/ui/src/ui/TabletScriptingInterface.h"
    ).read_text(encoding="utf-8")
    tablet_proxy_source = (
        ROOT / "libraries/ui/src/ui/TabletScriptingInterface.cpp"
    ).read_text(encoding="utf-8")
    window_root = (
        ROOT / "interface/resources/qml/hifi/tablet/WindowRoot.qml"
    ).read_text(encoding="utf-8")

    assert action_bar.count('objectName: "OverteTabletOpen"') == 1
    assert tablet_home.count('objectName: "OverteTabletClose"') == 1
    assert tablet_home.count('property string semanticId: "nav.close"') == 1
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
    assert native_bridge.count("#if defined(OVERTE_IOS_E2E_TEST_BUILD)") == 3
    assert "OverteIOSE2EAccessibilityButton : UIButton" in native_bridge
    assert "forControlEvents:UIControlEventTouchUpInside" in native_bridge
    assert "overlay.accessibilityElements = @[];" in native_bridge
    assert "button.frame = controlFrame;" in native_bridge
    assert "button.activationHandler = activationHandler;" in native_bridge
    assert "OverteTabletScreen.%s" in native_bridge
    assert "OverteTabletReady.%s" in native_bridge
    assert "OverteTabletControl.%s" in native_bridge
    assert "tabletE2EAccessibilityButtons" in native_bridge
    assert "QAccessibleActionInterface::pressAction()" in native_bridge
    assert "visibleTabletItem" in native_bridge
    assert "tabletItemFrame" in native_bridge
    assert 'item->property("semanticId").toString()' in native_bridge
    assert "QQuickItem* loadedItem = tabletRoot;" in native_bridge
    assert "tabletRoot->findChildren<QQuickItem*>()" in native_bridge
    assert 'item->property("semanticScreenId")' in native_bridge
    assert "observedScreen != screen" in native_bridge
    assert 'readonly property string semanticScreenId:' in window_root
    assert "getIOSTabletRoot" in tablet_proxy_header
    assert "QQuickItem* TabletProxy::getIOSTabletRoot() const" in tablet_proxy_source
    assert "OVERTE_IOS_E2E_TEST_BUILD" in application
    assert "tabletAccessibilityRefresh->setInterval(100)" in application
    for semantic_navigation_id in ("nav.back", "nav.home", "nav.close"):
        assert f'objectName: "{semantic_navigation_id}"' in window_root
    assert "returnToPreviousSemanticScreen" in window_root
    assert "tabletProxy.gotoHomeScreen()" in window_root
    assert "tabletProxy.hideAndroidTablet()" in window_root
    assert "#else\n    OverteIOSAccessibilityElement* element" in native_bridge
    assert native_bridge.count("UIAccessibilityPostNotification(") == 2
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
