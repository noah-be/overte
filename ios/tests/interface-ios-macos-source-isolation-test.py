#!/usr/bin/env python3
"""Contract excluding the macOS-only App Nap source from iOS Interface."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CMAKE = (ROOT / "interface/CMakeLists.txt").read_text()
SOURCE = (ROOT / "interface/src/AppNapDisabler.mm").read_text()
APPLICATION = (ROOT / "interface/src/Application.cpp").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


require('file(GLOB_RECURSE INTERFACE_OBJCPP_SRCS "src/*.m" "src/*.mm")' in CMAKE,
        "macOS Objective-C++ source discovery changed")
require('if (IOS)\n    # App Nap is a macOS process policy' in CMAKE,
        "App Nap source exclusion is not scoped to iOS")
require('get_filename_component(APP_NAP_DISABLER_MM "src/AppNapDisabler.mm" ABSOLUTE)' in CMAKE,
        "App Nap source is not resolved deterministically")
require("list(REMOVE_ITEM INTERFACE_OBJCPP_SRCS ${APP_NAP_DISABLER_MM})" in CMAKE,
        "App Nap source remains in the iOS Objective-C++ list")
require("#ifdef Q_OS_MAC" in SOURCE and "#import <AppKit/AppKit.h>" in SOURCE,
        "AppNapDisabler is no longer demonstrably macOS-only")
require("#if defined(Q_OS_MAC)\n// On Mac OS, disable App Nap" in APPLICATION,
        "desktop App Nap construction changed")

print("iOS macOS-source isolation valid: AppNapDisabler.mm excluded; desktop path preserved")
