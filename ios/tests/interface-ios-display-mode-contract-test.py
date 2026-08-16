#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

"""Keep the iOS client out of the desktop/XR first-launch chooser."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "interface/src/Application_Plugins.cpp").read_text(encoding="utf-8")
APPLICATION = (ROOT / "interface/src/Application.cpp").read_text(encoding="utf-8")
APPLICATION_SETUP = (ROOT / "interface/src/Application_Setup.cpp").read_text(encoding="utf-8")
APPLICATION_UI = (ROOT / "interface/src/Application_UI.cpp").read_text(encoding="utf-8")


def require(pattern: str, message: str, source: str = SOURCE) -> None:
    if re.search(pattern, source, re.MULTILINE | re.DOTALL) is None:
        raise SystemExit(message)


require(
    r"#if defined\(Q_OS_IOS\)\s+"
    r"// The iOS client ships one window-backed display plugin and no XR display\s+"
    r"// plugins\.[\s\S]*?"
    r"disabledLaunchPlugins\.push_back\(OPENVR_PLUGIN_NAME\);\s+"
    r"disabledLaunchPlugins\.push_back\(OPENXR_PLUGIN_NAME\);\s+"
    r"_previousPreferredDisplayMode\.set\(0\);\s+"
    r"#elif defined\(ANDROID_APP_PHONE_INTERFACE\)",
    "iOS no longer bypasses the desktop/XR display-mode chooser",
)
require(
    r"Setting::Handle<QString> activeDisplayPluginSetting[\s\S]*?"
    r"#if defined\(Q_OS_IOS\)\s+"
    r"// Ignore a stale desktop setting[\s\S]*?"
    r"activeDisplayPluginSetting\.set\(displayPlugins\.at\(0\)->getName\(\)\);\s+"
    r"#elif defined\(ANDROID_APP_PHONE_INTERFACE\)",
    "iOS can still restore an unavailable desktop/XR display setting",
)
require(
    r"auto defaultDisplayPlugin = displayPlugins\.at\(0\);[\s\S]*?"
    r"DisplayPluginPointer targetDisplayPlugin;\s+"
    r"#if defined\(Q_OS_IOS\)\s+"
    r"targetDisplayPlugin = defaultDisplayPlugin;\s+"
    r"#endif",
    "iOS does not deterministically select its sole supported display plugin",
)

ios_choice_branch = SOURCE.split("#if defined(Q_OS_IOS)", 1)[1].split(
    "#elif defined(ANDROID_APP_PHONE_INTERFACE)", 1
)[0]
for forbidden in ("QInputDialog", "setPreferredDisplayPlugins", "DESKTOP_DISPLAY_PLUGIN_NAME"):
    if forbidden in ios_choice_branch:
        raise SystemExit(f"iOS display selection still depends on desktop behavior: {forbidden}")

if not re.search(
    r"#if defined\(Q_OS_IOS\) \|\| defined\(ANDROID_APP_PHONE_INTERFACE\)\s+"
    r"// Mobile window managers own the screen bounds\.[\s\S]*?"
    r"_window->showFullScreen\(\);\s+#else\s+"
    r"_window->restoreGeometry\(\);\s+_window->setVisible\(true\);",
    APPLICATION_SETUP,
    re.MULTILINE,
):
    raise SystemExit("iOS can still restore an offset desktop window instead of claiming the screen")

if not re.search(
    r"#if defined\(Q_OS_IOS\) \|\| defined\(ANDROID_APP_PHONE_INTERFACE\)\s+"
    r"// The native desktop menu bar[\s\S]*?"
    r"Menu::getInstance\(\)->setVisible\(false\);\s+#else\s+"
    r"Menu::getInstance\(\)->setVisible\(_menuBarVisible\.get\(\)\);",
    APPLICATION,
    re.MULTILINE,
):
    raise SystemExit("iOS startup can still expose the native desktop menu bar")

require(
    r"void Application::setMenuBarVisible\(bool visible\)[\s\S]*?"
    r"#if defined\(Q_OS_IOS\)[\s\S]*?visible = false;\s+#endif\s+"
    r"auto\* menuBar = qApp->getWindow\(\)->menuBar\(\);",
    "iOS scripts or persisted settings can reveal desktop menu chrome",
    APPLICATION_UI,
)

print("PASS iOS deterministic display-plugin selection contract")
