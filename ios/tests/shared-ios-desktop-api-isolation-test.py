#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GPU_IDENT = (ROOT / "libraries/shared/src/GPUIdent.cpp").read_text(encoding="utf-8")
MAC_HELPER = (ROOT / "libraries/shared/src/shared/platform/MacHelper.cpp").read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


desktop_guard = "defined(Q_OS_MAC) && !defined(Q_OS_IOS)"
require(GPU_IDENT.count(desktop_guard) >= 2,
        "GPUIdent macOS includes and implementation must both exclude iOS")
for token in ("<OpenGL/OpenGL.h>", "CGLQueryRendererInfo", "system_profiler"):
    position = GPU_IDENT.index(token)
    require(GPU_IDENT.rfind(desktop_guard, 0, position) >= 0,
            f"GPUIdent desktop token is not behind the iOS exclusion: {token}")

for token in ("<IOKit/IOMessage.h>", "IORegisterForSystemPower", "IOAllowPowerChange"):
    position = MAC_HELPER.index(token)
    require(MAC_HELPER.rfind(desktop_guard, 0, position) >= 0,
            f"MacHelper desktop token is not behind the iOS exclusion: {token}")
require("#elif defined(Q_OS_IOS)" in MAC_HELPER and
        "DependencyManager::set<PlatformHelper, IOSPlatformHelper>()" in MAC_HELPER,
        "iOS must retain a conservative PlatformHelper dependency")
require("application delegate" in MAC_HELPER and "without claiming desktop sleep/wake events" in MAC_HELPER,
        "the iOS fallback must document lifecycle ownership and fail-closed semantics")

print("shared iOS desktop API isolation valid: CGL/system_profiler and IOKit excluded")
