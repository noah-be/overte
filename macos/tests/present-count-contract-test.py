#!/usr/bin/env python3
"""Keep display present counters tied to completed output operations."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def function(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    end = source.index(next_signature, start)
    return source[start:end]


opengl_source = (
    ROOT / "libraries/display-plugins/src/display-plugins/OpenGLDisplayPlugin.cpp"
).read_text(encoding="utf-8")
opengl = function(
    opengl_source,
    "void OpenGLDisplayPlugin::present(",
    "float OpenGLDisplayPlugin::newFramePresentRate()",
)
opengl_prefix, opengl_frames = opengl.split("if (_currentFrame) {", 1)
opengl_frame, opengl_always = opengl_frames.split("} else if (alwaysPresent()) {", 1)
if "incrementPresentCount()" in opengl_prefix:
    raise SystemExit("OpenGL must not publish a present before executing its frame")
for earlier, later in (
    ("_gpuContext->executeFrame(_currentFrame)", "snapshotOperators"),
    ("snapshotOperators", "internalPresent()"),
    ("internalPresent()", "incrementPresentCount()"),
):
    if opengl_frame.index(earlier) >= opengl_frame.index(later):
        raise SystemExit(f"OpenGL completed-present ordering is invalid: {earlier}")
if opengl_always.index("internalPresent()") >= opengl_always.index(
    "incrementPresentCount()"
):
    raise SystemExit("OpenGL always-present path publishes before output completes")
if opengl.count("incrementPresentCount()") != 2:
    raise SystemExit("OpenGL must publish exactly its two completed output paths")

vulkan_source = (
    ROOT / "libraries/display-plugins/src/display-plugins/VulkanDisplayPlugin.cpp"
).read_text(encoding="utf-8")
vulkan = function(
    vulkan_source,
    "void VulkanDisplayPlugin::present(",
    "float VulkanDisplayPlugin::newFramePresentRate()",
)
vulkan_prefix, vulkan_frames = vulkan.split("if (_currentFrame) {", 1)
vulkan_frame, vulkan_always = vulkan_frames.split("} else if (alwaysPresent()) {", 1)
if "incrementPresentCount()" in vulkan_prefix:
    raise SystemExit("Vulkan must not publish a present before executing its frame")
if vulkan_frame.index("_swapchain.queuePresent") >= vulkan_frame.index(
    "incrementPresentCount()"
):
    raise SystemExit("Vulkan publishes a present before queueing completed output")
if vulkan_always.index("internalPresent()") >= vulkan_always.index(
    "incrementPresentCount()"
):
    raise SystemExit("Vulkan always-present path publishes before output completes")
if vulkan.count("incrementPresentCount()") != 2:
    raise SystemExit("Vulkan must publish exactly its two completed output paths")

test_header = (
    ROOT / "interface/src/scripting/TestScriptingInterface.h"
).read_text(encoding="utf-8")
if "Number of presents completed by the active display plugin" not in test_header:
    raise SystemExit("Test present-count documentation must describe completed output")

print("display completed-present counter contract valid")
