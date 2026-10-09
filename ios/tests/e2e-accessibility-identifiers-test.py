#!/usr/bin/env python3
"""Static contract for the shared QML controls used by physical iOS E2E."""

# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def preprocess_native_bridge(source: str, test_build: bool, ios: bool = False) -> str:
    # Exercise the real preprocessor guards without requiring UIKit/Qt headers
    # on the host. No native compilation or device acceptance is claimed here.
    source = re.sub(r'^\s*#(?:include|import)\s+.*$', '', source, flags=re.MULTILINE)
    command = ['c++', '-E', '-P', '-x', 'c++', '-']
    if test_build:
        command.append('-DOVERTE_IOS_E2E_TEST_BUILD=1')
    if ios:
        command.append('-DQ_OS_IOS=1')
    return subprocess.run(command, input=source, capture_output=True,
                          text=True, check=True, timeout=10).stdout


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
        ROOT / "ios/ui/IOSTouchUiMetrics.mm"
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
    assert 'if ("id" in Accessible)' in button_qml and "Accessible.id = Qt.binding(function() { return objectName })" in button_qml
    assert "property string accessibleName: text" in button_qml
    assert 'property string accessibleDescription: ""' in button_qml
    assert "Accessible.name: accessibleName" in button_qml
    assert "Accessible.description: accessibleDescription" in button_qml
    assert "Accessible.onPressAction: button.clicked()" in button_qml
    assert "activeFocusOnTab: true" in button_qml
    assert 'if ("id" in Accessible)' in tablet_home and "Accessible.id = Qt.binding(function() { return objectName })" in tablet_home
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
    production_bridge = preprocess_native_bridge(native_bridge, False)
    test_bridge = preprocess_native_bridge(native_bridge, True)
    for test_only_symbol in ('OverteIOSE2EAccessibilityButton',
                             'tabletE2EAccessibilityButton',
                             'observeIOSNativeAccessibility'):
        assert test_only_symbol not in production_bridge, test_only_symbol
        assert test_only_symbol in test_bridge, test_only_symbol
    test_interface = (ROOT / "interface/src/scripting/TestScriptingInterface.cpp").read_text()
    ordinary_interface = preprocess_native_bridge(test_interface, False, True)
    enabled_interface = preprocess_native_bridge(test_interface, True, True)
    for symbol in ("iosNativeUiSnapshot", "iosTextTest", "iosRenderObservation", "iosEntityScriptConsentTest"):
        assert "TestScriptingInterface::" + symbol not in ordinary_interface
        assert "TestScriptingInterface::" + symbol in enabled_interface
    assert 'OverteIOSAccessibilityElement' in production_bridge
    assert 'updateIOSTabletAccessibilityControls' in production_bridge
    assert "OverteIOSE2EAccessibilityButton : UIButton" in native_bridge
    assert "forControlEvents:UIControlEventTouchUpInside" in native_bridge
    assert "overlay.accessibilityElements = @[];" in native_bridge
    assert "button.frame = controlFrame;" in native_bridge
    assert "button.activationHandler = activationHandler;" in native_bridge
    assert "tabletCloseControl(tablet->getIOSTabletRoot())" in native_bridge
    assert "button.hidden = CGRectIsNull(controlFrame) || CGRectIsEmpty(controlFrame);" in native_bridge
    assert "button.enabled = !button.hidden;" in native_bridge
    assert "OverteTabletScreen.%s" in native_bridge
    assert "OverteTabletReady.%s" in native_bridge
    assert "OverteTabletControl.%s" in native_bridge
    assert "tabletE2EAccessibilityButtons" in native_bridge
    assert "QAccessibleActionInterface::pressAction()" in native_bridge
    assert "visibleTabletItem" in native_bridge
    assert "tabletItemFrame" in native_bridge
    assert 'item->property("semanticId").toString()' in native_bridge
    assert "QQuickItem* loadedItem = tabletRoot;" in native_bridge
    assert "tabletVisualItems" in native_bridge
    assert "items.at(index)->childItems()" in native_bridge
    assert "tabletRoot->findChildren<QQuickItem*>()" not in native_bridge
    assert 'item->property("semanticScreenId")' in native_bridge
    assert "observedScreen != screen" in native_bridge
    assert 'readonly property string semanticScreenId:' in window_root
    assert "getIOSTabletRoot" in tablet_proxy_header
    assert "QQuickItem* TabletProxy::getIOSTabletRoot() const" in tablet_proxy_source
    assert "OVERTE_IOS_E2E_TEST_BUILD" in application
    assert "tabletAccessibilityRefresh->setInterval(100)" in application
    navigation = (ROOT / "interface/resources/qml/hifi/tablet/TabletNavigation.qml").read_text()
    assert "footer: TabletNavigation" in window_root
    assert 'objectName: "nav." + modelData.key' in navigation
    for semantic_navigation_key in ("back", "home", "close"):
        assert f'key: "{semantic_navigation_key}"' in navigation
    assert "returnToPreviousSemanticScreen" in window_root
    assert "tabletProxy.gotoHomeScreen()" in window_root
    assert "tabletProxy.hideAndroidTablet()" in window_root
    assert "#else\n    OverteIOSAccessibilityElement* element" in native_bridge
    assert native_bridge.count("UIAccessibilityPostNotification(") == 2
    assert re.search(
        r'set_source_files_properties\(\s*'
        r'"\$\{IOS_TOUCH_UI_METRICS_MM\}"\s*'
        r'PROPERTIES\s+COMPILE_OPTIONS\s+"-fobjc-arc"\s*\)',
        interface_cmake,
    )
    assert '${CMAKE_CURRENT_SOURCE_DIR}/../ios/ui/IOSTouchUiMetrics.mm' in interface_cmake
    assert 'list(APPEND INTERFACE_OBJCPP_SRCS "${IOS_TOUCH_UI_METRICS_MM}")' in interface_cmake
    assert "updateIOSTabletAccessibilityControls(systemTablet" in application
    assert "&TabletProxy::tabletShownChanged" in application
    print("PASS stable iOS tablet accessibility identifiers")


if __name__ == "__main__":
    main()
