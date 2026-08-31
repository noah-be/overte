#!/usr/bin/env python3
"""Fail-closed contract for explicit GL links still required by iOS sources."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]

sources = {
    "libraries/qml/src/qml/impl/SharedObject.cpp": ("initializeRenderControl(QOpenGLContext* context)",),
    "libraries/qml/src/qml/impl/RenderEventHandler.cpp": ("QOpenGLContextWrapper::currentContext()",),
    "interface/src/Application_Graphics.cpp": ("#include <gl/GLHelpers.h>", "OffscreenGLCanvas* qmlShareContext"),
}
for relative, anchors in sources.items():
    text = (ROOT / relative).read_text(encoding="utf-8")
    for anchor in anchors:
        if anchor not in text:
            raise SystemExit(f"GL debt anchor {anchor!r} disappeared from {relative}; update migration inventory")

interface_cmake = (ROOT / "interface/CMakeLists.txt").read_text(encoding="utf-8")
display_cmake = (ROOT / "libraries/display-plugins/CMakeLists.txt").read_text(encoding="utf-8")
if 'set(INTERFACE_GL_LIBRARY "")' not in interface_cmake:
    raise SystemExit("Interface iOS Vulkan gl link is not explicitly cleared")
if "${INTERFACE_GL_LIBRARY}" not in interface_cmake:
    raise SystemExit("Interface link list bypasses the gated GL library variable")
if 'set(DISPLAY_PLUGINS_GL_LIBRARY "")' not in display_cmake:
    raise SystemExit("display-plugins iOS Vulkan gl link is not explicitly cleared")
if "${DISPLAY_PLUGINS_GL_LIBRARY}" not in display_cmake:
    raise SystemExit("display-plugins link list bypasses the gated GL library variable")

print("iOS explicit GL API debt valid: both direct links removed; target-owned QML/vk compatibility debt remains")
