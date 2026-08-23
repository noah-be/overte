#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEADER = (ROOT / "interface/src/IOSTouchUiMetrics.h").read_text()
SOURCE = (ROOT / "interface/src/IOSTouchUiMetrics.mm").read_text()
PROFILE = (ROOT / "interface/resources/qml/controlsUit/+ios/TouchUiProfile.qml").read_text()
GRAPHICS = (ROOT / "interface/src/Application_Graphics.cpp").read_text()
APPLICATION_EVENTS = (ROOT / "interface/src/Application_Events.cpp").read_text()
APPLICATION_UI = (ROOT / "interface/src/Application_UI.cpp").read_text()
SELECTORS = (ROOT / "libraries/shared/src/shared/FileUtils.cpp").read_text()
TABLET_HEADER = (ROOT / "libraries/ui/src/ui/TabletScriptingInterface.h").read_text()
TABLET_SOURCE = (ROOT / "libraries/ui/src/ui/TabletScriptingInterface.cpp").read_text()
LOGIN_HEADER = (ROOT / "interface/src/ui/LoginDialog.h").read_text()
LOGIN_SOURCE = (ROOT / "interface/src/ui/LoginDialog.cpp").read_text()
DIALOGS = (ROOT / "interface/src/ui/DialogsManager.cpp").read_text()
BUTTON = (ROOT / "interface/resources/qml/controlsUit/Button.qml").read_text()
DESKTOP = (ROOT / "interface/resources/qml/desktop/Desktop.qml").read_text()
WRAPPED_MENU = (ROOT / "interface/resources/qml/controls/WrappedMenu.qml").read_text()
VR_MENU = (ROOT / "libraries/ui/src/VrMenu.cpp").read_text()
IOS_STATS = (ROOT / "interface/resources/qml/+ios/Stats.qml").read_text()
PHONE_LOGIN = (ROOT / "interface/resources/qml/LoginDialog/+android_phoneInterface/LinkAccountBody.qml").read_text()
APPLICATION_OVERLAY = (ROOT / "interface/src/ui/ApplicationOverlay.cpp").read_text()
INPUT_PLUGINS = (ROOT / "libraries/input-plugins/src/input-plugins/InputPlugin.cpp").read_text()
VIRTUAL_PAD = (ROOT / "libraries/input-plugins/src/input-plugins/TouchscreenVirtualPadDevice.cpp").read_text()
VIRTUAL_PAD_HEADER = (ROOT / "libraries/input-plugins/src/input-plugins/TouchscreenVirtualPadDevice.h").read_text()
VIRTUAL_PAD_MANAGER = (ROOT / "libraries/ui/src/VirtualPadManager.h").read_text()
STATS_SOURCE = (ROOT / "interface/src/ui/Stats.cpp").read_text()
OFFSCREEN_UI = (ROOT / "libraries/ui/src/OffscreenUi.cpp").read_text()
RENDER_HEADER = (ROOT / "interface/src/scripting/RenderScriptingInterface.h").read_text()
RENDER_SOURCE = (ROOT / "interface/src/scripting/RenderScriptingInterface.cpp").read_text()
GRAPHICS_SETTINGS = (ROOT / "scripts/system/settings/qml/pages/GraphicsSettings.qml").read_text()
TABLET_HOME = (ROOT / "interface/resources/qml/hifi/tablet/TabletHome.qml").read_text()

for metric in (
    "safeInsetLeft", "safeInsetTop", "safeInsetRight", "safeInsetBottom",
    "imeInsetBottom", "keyboardVisible", "surfaceWidth", "surfaceHeight",
    "density", "fontScale",
):
    assert f"Q_PROPERTY(" in HEADER and metric in HEADER
    assert f"runtimeMetrics.{metric}" in PROFILE

for native_contract in (
    "safeAreaInsets", "UIKeyboardWillChangeFrameNotification",
    "UIKeyboardWillHideNotification", "UIContentSizeCategoryDidChangeNotification",
    "UIWindowDidBecomeKeyNotification", "QTimer::singleShot",
    "CGRectIntersection", "window.screen.scale",
    "[window endEditing:YES]",
):
    assert native_contract in SOURCE

for capability in (
    "directTouch: true", "systemImeAvailable: true",
    "screenSpacePresentation: true", "vrAudioAvailable: false",
    "controllerSettingsAvailable: false", "navigationPreferencesAvailable: true",
):
    assert capability in PROFILE

assert 'qmlRegisterSingletonType<IOSTouchUiMetrics>' in SOURCE
assert "registerIOSTouchUiMetricsQmlType();" in GRAPHICS
assert "new IOSTouchUiMetrics(this)" in GRAPHICS
assert "setTouchUiRuntimeMetrics(metrics)" in GRAPHICS
assert "OVERTE_IOS_TOUCH_UI_GATE stage=native-metrics-published" in GRAPHICS
assert 'extraSelectors << "ios" << "mobile" << "touch"' in SELECTORS
assert "android_phoneInterface" in SELECTORS
assert 'import ".." as SharedControls' in PROFILE
assert "SharedControls.TouchUiProfileBase" in PROFILE
assert "graphicsSettingsAvailable: true" in PROFILE

mobile_guard = "defined(ANDROID_APP_PHONE_INTERFACE) || defined(Q_OS_IOS)"
assert mobile_guard in TABLET_HEADER
assert mobile_guard in TABLET_SOURCE
assert "touchUiAutoOpenTablet" in TABLET_SOURCE
assert "OVERTE_IOS_TOUCH_UI_GATE stage=metrics-ready" in TABLET_SOURCE
assert "OVERTE_IOS_TOUCH_UI_GATE stage=tablet-visible" in TABLET_SOURCE
assert "OVERTE_IOS_TOUCH_UI_GATE stage=button-registered" in TABLET_SOURCE
assert mobile_guard in LOGIN_HEADER
assert mobile_guard in LOGIN_SOURCE
assert mobile_guard in DIALOGS
assert "defined(Q_OS_ANDROID) || defined(Q_OS_IOS)" in APPLICATION_UI
assert "scriptEngines->loadDefaultScripts();" in APPLICATION_UI
assert "dismissIOSKeyboard();" in APPLICATION_UI
assert "defined(ANDROID_APP_PHONE_INTERFACE) || defined(Q_OS_IOS)" in GRAPHICS
assert 'Qt.platform.os === "android" || Qt.platform.os === "ios"' in BUTTON

assert "OverteControls.WrappedMenu" in DESKTOP
assert "addMenuWrap" in WRAPPED_MENU and "addItemWrap" in WRAPPED_MENU
assert 'loadUrl(PathUtils::qmlUrl("controls/WrappedMenu.qml"))' in VR_MENU
assert 'loadFromModule("QtQuick.Controls", "MenuItem")' in VR_MENU
assert 'loadFromModule("QtQuick.Controls", "MenuSeparator")' in VR_MENU

assert "Position:" in IOS_STATS
assert "Present:" in IOS_STATS
assert "Entities local/server:" in IOS_STATS
assert "GPU memory tex/buf:" in IOS_STATS
assert 'iosRuntimeDiagnosticBool("statsOverlay", true)' in APPLICATION_UI
assert 'iosRuntimeDiagnosticBool("statsOverlayExpanded", true)' in APPLICATION_UI
assert '"statsOverlayExpandDelayMs", 5000, 0, 30000' in APPLICATION_UI
assert "stage=expanded" in APPLICATION_UI
assert "if (!nodeList || !avatarManager || !avatarManager->getMyAvatar())" in STATS_SOURCE
assert "if (audioMixerNode && audioClient)" in STATS_SOURCE

assert "defined(Q_OS_ANDROID) || defined(Q_OS_IOS)" in INPUT_PLUGINS
assert "new TouchscreenVirtualPadDevice()" in INPUT_PLUGINS
assert "defined(ANDROID_APP_PHONE_INTERFACE) || defined(Q_OS_IOS)" in VIRTUAL_PAD
assert 'touchscreenvirtualpad-phone.json' in VIRTUAL_PAD
assert "OVERTE_IOS_TOUCH_INPUT_GATE stage=virtual-pad-initialized" in VIRTUAL_PAD
assert "qApp->focusWindow()" in VIRTUAL_PAD
assert 'qApp->property("overteIosSafeInsetBottom")' in VIRTUAL_PAD
assert "_safeBottomInset == safeBottomInset" in VIRTUAL_PAD
assert "int _safeBottomInset { -1 }" in VIRTUAL_PAD_HEADER
assert 'qApp->setProperty("overteIosSafeInsetBottom"' in GRAPHICS
assert "forwardMobileTouchToOffscreenUi" in APPLICATION_EVENTS
assert "handleMobilePointerEvent" in APPLICATION_EVENTS
assert 'tablet->property("tabletShown").toBool()' in APPLICATION_EVENTS
assert "stage=offscreen-touch-forwarded" in APPLICATION_EVENTS
assert 'tabletVisible ? "tablet" : "address"' in APPLICATION_EVENTS
assert "ui/TabletScriptingInterface.h" not in VIRTUAL_PAD
assert "effectiveBottomMargin = _extraBottomMargin + safeBottomInset" in VIRTUAL_PAD
assert 'iosRuntimeDiagnosticInt(\n        "touchLookSensitivityPercent", 400, 50, 1200)' in VIRTUAL_PAD
assert "_buttonsManager.buttons[0].buttonPosition = jumpButtonPosition" in VIRTUAL_PAD
assert "OVERTE_IOS_TOUCH_INPUT_GATE stage=button-pressed" in VIRTUAL_PAD
assert APPLICATION_EVENTS.index("forwardMobileTouchToOffscreenUi") >= 0
assert VIRTUAL_PAD.index("findStartingTouchPointCandidate") < VIRTUAL_PAD.index(
    "idxViewStartingPointCandidate = i"
)
assert "QEvent::MouseButtonPress" in OFFSCREEN_UI
assert "QCoreApplication::sendEvent(getWindow(), &mouseEvent)" in OFFSCREEN_UI
assert 'settingText: "Resolution scale"' in GRAPHICS_SETTINGS
assert "Render.viewportResolutionScale = value.toFixed(1)" in GRAPHICS_SETTINGS
assert '"viewportResolutionScale", 0.8f' in RENDER_HEADER
assert '"iosViewportResolutionScaleDefaultApplied", false' in RENDER_SOURCE
assert "_viewportResolutionScale = 0.8f" in RENDER_SOURCE
assert "OVERTE_IOS_RENDER_PROFILE stage=resolution-scale-applied" in RENDER_SOURCE
assert "onClicked: modelData.clicked()" in TABLET_HOME
assert "onClicked: tabletProxy.hideAndroidTablet()" in TABLET_HOME
assert "UITextInputAssistantItem" in SOURCE
assert "assistant.leadingBarButtonGroups = @[]" in SOURCE
assert "QTimer::singleShot(1000" in APPLICATION_UI
MOBILE_ACTION_BAR = (ROOT / "scripts/system/+android_phoneInterface/mobileActionBar.js").read_text()
assert "shortEdge * 0.105" in MOBILE_ACTION_BAR
assert "Controller.touchBeginEvent.connect(onTouchBegin)" in MOBILE_ACTION_BAR
assert 'OVERTE_MOBILE_ACTION_BAR action=' in MOBILE_ACTION_BAR
assert "bool _hidden { false };" in VIRTUAL_PAD_MANAGER
assert "renderIOSVirtualPad(renderArgs)" in APPLICATION_OVERLAY
assert 'metrics.value("safeInsetTop")' in APPLICATION_OVERLAY
assert "point -= glm::vec2(safeLeft, safeTop)" in APPLICATION_OVERLAY
assert "OVERTE_IOS_TOUCH_UI_GATE stage=virtual-pad-composited" in APPLICATION_OVERLAY
for texture in ("analog_stick.png", "analog_stick_base.png", "fly.png", "handshake.png"):
    assert texture in APPLICATION_OVERLAY

for startup_qml in (
    PROFILE,
    BUTTON,
    DESKTOP,
    WRAPPED_MENU,
    PHONE_LOGIN,
    IOS_STATS,
    (ROOT / "interface/resources/qml/controlsUit/TextField.qml").read_text(),
    (ROOT / "interface/resources/qml/hifi/tablet/TabletHome.qml").read_text(),
    (ROOT / "interface/resources/qml/hifi/tablet/TabletMenu.qml").read_text(),
    (ROOT / "interface/resources/qml/hifi/tablet/TabletMenuItem.qml").read_text(),
    (ROOT / "interface/resources/qml/hifi/tablet/TabletMenuStack.qml").read_text(),
):
    assert "import QtQuick.Controls 1." not in startup_qml
    assert "import QtQuick.Controls.Styles 1." not in startup_qml

print("iOS touch UI adapter contract valid: UIKit metrics, screen-space host, Qt 6 menus, mobile dialogs and expanded diagnostics")
