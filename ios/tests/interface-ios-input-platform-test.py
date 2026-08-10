#!/usr/bin/env python3
"""Contract keeping macOS native-window mouse workarounds out of iOS."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "interface/src/Application_Events.cpp").read_text()
UI_SOURCE = (ROOT / "interface/src/Application_UI.cpp").read_text()
UI_UTIL_SOURCE = (ROOT / "interface/src/UIUtil.cpp").read_text()
MAC_DESKTOP_GUARD = "#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


require(SOURCE.count(MAC_DESKTOP_GUARD) == 2,
        "expected both macOS native-window mouse workarounds to exclude iOS")
require("Cmd+LeftClick is treated as a RightClick" in SOURCE and
        "mouseEvent->modifiers() == Qt::MetaModifier" in SOURCE,
        "desktop Cmd-click workaround changed")
require("Fix for OSX right click dragging on window" in SOURCE and
        "event->button() == Qt::MouseButton::RightButton" in SOURCE,
        "desktop right-drag focus workaround changed")
require("#if defined(Q_OS_MAC)\n" not in SOURCE,
        "an unqualified macOS branch remains in Application_Events.cpp")
require(MAC_DESKTOP_GUARD in UI_SOURCE and
        "auto cursorTarget = _window; // OSX doesn't seem to provide" in UI_SOURCE,
        "macOS GL-widget cursor workaround is not explicitly excluded on iOS")
require("#else\n        // On windows and linux" in UI_SOURCE and
        "auto cursorTarget = _primaryWidget;" in UI_SOURCE,
        "backend-normal primary cursor target changed")
require(MAC_DESKTOP_GUARD in UI_UTIL_SOURCE and
        "// The height on OSX is 4 pixels too tall\n    titleBarHeight -= 4;" in UI_UTIL_SOURCE,
        "macOS title-bar metric workaround is not explicitly excluded on iOS")
require("#if defined(Q_OS_MAC) || defined(Q_OS_IOS)\n"
        "    // macOS and iOS both expose point-sized UI fonts." in UI_UTIL_SOURCE,
        "iOS point-sized fonts fall through to desktop 96-DPI scaling")
require("const float BASE_DPI = 72.0f;" in UI_UTIL_SOURCE and
        "const float NATIVE_DPI = 72.0f;" in UI_UTIL_SOURCE and
        "float fontScale = BASE_DPI / NATIVE_DPI;" in UI_UTIL_SOURCE,
        "iOS font scaling no longer resolves to the documented 1.0 factor")

print("iOS input platform contract valid: desktop workarounds excluded; iOS point-font scale preserved")
