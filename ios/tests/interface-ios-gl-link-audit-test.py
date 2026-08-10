#!/usr/bin/env python3
"""Audit migrated Interface GL consumers after direct-link removal."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CMAKE = (ROOT / "interface/CMakeLists.txt").read_text()
HANDLER = (ROOT / "interface/src/graphics/RenderEventHandler.h").read_text()
GRAPHICS = (ROOT / "interface/src/Application_Graphics.cpp").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


require('set(INTERFACE_GL_LIBRARY "")' in CMAKE,
        "Interface iOS Vulkan GL library is not cleared")
require("OffscreenGLCanvas" not in HANDLER and '"gl/' not in HANDLER,
        "RenderEventHandler still carries an unused GL canvas dependency")

# Desktop compatibility remains source-guarded while iOS fails QML closed.
require("OffscreenGLCanvas* qmlShareContext" in GRAPHICS,
        "desktop QML shared-context compatibility changed")
require("glClear(GL_COLOR_BUFFER_BIT);" in GRAPHICS,
        "desktop legacy clear compatibility changed")
require("#if !defined(Q_OS_IOS)\n    glClearColor" in GRAPHICS,
        "legacy clear consumer is not iOS-gated")

print("Interface GL link audit valid: direct link removed; desktop compatibility remains guarded")
