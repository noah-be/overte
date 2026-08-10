#!/usr/bin/env python3
"""Contract for removing GL implementations, not shared GL APIs, from iOS."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
root_cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
interface_cmake = (ROOT / "interface/CMakeLists.txt").read_text(encoding="utf-8")
display_cmake = (ROOT / "libraries/display-plugins/CMakeLists.txt").read_text(encoding="utf-8")
gl_ui_source = (ROOT / "interface/src/ui/ResourceImageItem.h").read_text(encoding="utf-8")

ios_vulkan = root_cmake.index("if(IOS)", root_cmake.index('elseif (OVERTE_RENDERING_BACKEND STREQUAL "Vulkan")'))
other_platform = root_cmake.index("else()", ios_vulkan)
ios_branch = root_cmake[ios_vulkan:other_platform]
for token in ('OVERTE_IOS_VULKAN_NATIVE_TARGETS gpu-vk vk', 'OVERTE_IOS_VULKAN_LEGACY_GL_BRIDGE_TARGETS ""'):
    if token not in ios_branch:
        raise SystemExit(f"iOS platform backend contract missing {token!r}")
if "gpu-gl-common gpu-gl" in ios_branch:
    raise SystemExit("iOS platform backend still selects OpenGL implementations")

# Internal GL-typed UI debt remains explicit and must not be conflated with the
# removed backend implementations. The public plugin ABI itself is neutral.
if " shared workload task octree ktx gpu gl procedural" not in interface_cmake:
    raise SystemExit("Interface explicit shared gl link unexpectedly changed")
if "link_hifi_libraries(shared shaders plugins ui-plugins gl ui" not in display_cmake:
    raise SystemExit("display-plugins explicit shared gl link unexpectedly changed")
for token in ("QOpenGLFramebufferObject", "GLsync"):
    if token not in gl_ui_source:
        raise SystemExit(f"internal GL UI evidence missing {token}")

print("iOS Vulkan platform backend valid: gpu-vk/vk only; explicit shared GL API debt preserved")
