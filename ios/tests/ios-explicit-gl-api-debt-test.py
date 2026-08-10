#!/usr/bin/env python3
"""Fail-closed contract for explicit GL links still required by iOS sources."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]

sources = {
    "libraries/plugins/src/plugins/DisplayPlugin.h": (
        "struct QuickTextureCopyTarget",
        "void** completionToken",
    ),
    "interface/src/ui/ResourceImageItem.h": (
        "QOpenGLFramebufferObject* _copyFbo",
        "GLsync _fenceSync",
    ),
    "interface/src/ui/ResourceImageItem.cpp": (
        "glWaitSync(_fenceSync",
        "glDeleteSync(_fenceSync",
    ),
    "libraries/display-plugins/src/display-plugins/VulkanDisplayPlugin.cpp": (
        "#include <gl/Context.h>",
        "gpu::gl::getFreeDedicatedMemory()",
    ),
    "interface/src/Application_Graphics.cpp": ("#include <gl/GLHelpers.h>",),
}
for relative, anchors in sources.items():
    text = (ROOT / relative).read_text(encoding="utf-8")
    for anchor in anchors:
        if anchor not in text:
            raise SystemExit(f"GL debt anchor {anchor!r} disappeared from {relative}; update migration inventory")

interface_cmake = (ROOT / "interface/CMakeLists.txt").read_text(encoding="utf-8")
display_cmake = (ROOT / "libraries/display-plugins/CMakeLists.txt").read_text(encoding="utf-8")
if " shared workload task octree ktx gpu gl procedural" not in interface_cmake:
    raise SystemExit("Interface gl link removed while source-level GL debt remains")
if "link_hifi_libraries(shared shaders plugins ui-plugins gl ui" not in display_cmake:
    raise SystemExit("display-plugins gl link removed while source-level GL debt remains")

print("iOS explicit GL API debt valid: 5 source boundaries keep 2 links fail-closed")
