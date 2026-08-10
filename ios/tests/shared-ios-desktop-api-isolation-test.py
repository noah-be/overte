#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GPU_IDENT = (ROOT / "libraries/shared/src/GPUIdent.cpp").read_text(encoding="utf-8")
MAC_HELPER = (ROOT / "libraries/shared/src/shared/platform/MacHelper.cpp").read_text(encoding="utf-8")
PATH_UTILS = (ROOT / "libraries/shared/src/PathUtils.cpp").read_text(encoding="utf-8")
INTERFACE_CMAKE = (ROOT / "interface/CMakeLists.txt").read_text(encoding="utf-8")


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

require('#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)\n'
        '        static const QString staticResourcePath = QCoreApplication::applicationDirPath() + "/../Resources/";'
        in PATH_UTILS,
        "the macOS Contents/Resources layout must be unreachable on iOS")
require('#else\n        static const QString staticResourcePath = QCoreApplication::applicationDirPath() + "/resources/";'
        in PATH_UTILS,
        "iOS must resolve /~/ through the executable-adjacent resources directory")
require('if (APPLE AND NOT IOS)' in INTERFACE_CMAKE and
        'set(RESOURCES_DEV_DIR "${INTERFACE_EXEC_DIR}/resources")' in INTERFACE_CMAKE and
        '"${RESOURCES_DEV_DIR}/serverless/tutorial.json"' in INTERFACE_CMAKE,
        "the iOS resource resolver must match Interface's packaged tutorial location")

print("shared iOS desktop API isolation valid: desktop APIs and macOS resource layout excluded")
