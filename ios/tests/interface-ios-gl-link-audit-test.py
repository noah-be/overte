#!/usr/bin/env python3
"""Fail-closed audit for the remaining explicit Interface gl dependency."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CMAKE = (ROOT / "interface/CMakeLists.txt").read_text()
HANDLER = (ROOT / "interface/src/graphics/RenderEventHandler.h").read_text()
GRAPHICS = (ROOT / "interface/src/Application_Graphics.cpp").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


link_block = CMAKE.split("link_hifi_libraries(", 1)[1].split(")", 1)[0]
require(" gpu gl procedural " in link_block.replace("\n", " "),
        "Interface gl link changed before the remaining consumers were migrated")
require("OffscreenGLCanvas" not in HANDLER and '"gl/' not in HANDLER,
        "RenderEventHandler still carries an unused GL canvas dependency")

# These are source-anchored reasons why deleting the link is not yet honest.
require("OffscreenGLCanvas* qmlShareContext" in GRAPHICS,
        "QML shared-context consumer moved; update this audit")
require("glClear(GL_COLOR_BUFFER_BIT);" in GRAPHICS,
        "legacy clear consumer moved; update this audit")

print("Interface GL link audit valid: telemetry isolated; active QML/clear consumers remain fail-closed")
