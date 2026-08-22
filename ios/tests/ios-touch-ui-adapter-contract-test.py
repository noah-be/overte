#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEADER = (ROOT / "interface/src/IOSTouchUiMetrics.h").read_text()
SOURCE = (ROOT / "interface/src/IOSTouchUiMetrics.mm").read_text()
PROFILE = (ROOT / "interface/resources/qml/controlsUit/+ios/TouchUiProfile.qml").read_text()
GRAPHICS = (ROOT / "interface/src/Application_Graphics.cpp").read_text()
SELECTORS = (ROOT / "libraries/shared/src/shared/FileUtils.cpp").read_text()

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
    "CGRectIntersection", "window.screen.scale",
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
assert 'extraSelectors << "ios" << "mobile" << "touch"' in SELECTORS
assert "android_phoneInterface" in SELECTORS

print("iOS touch UI adapter contract valid: live UIKit geometry and centralized capabilities")
