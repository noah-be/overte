#!/usr/bin/env python3
"""Contract for the Vulkan-only iOS platform and gated direct GL links."""

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

# Both top-level direct links are empty only for iOS Vulkan; target-owned qml/vk
# compatibility dependencies remain separately audited.
for text, anchors in (
    (interface_cmake, ('set(INTERFACE_GL_LIBRARY gl)', 'set(INTERFACE_GL_LIBRARY "")', '${INTERFACE_GL_LIBRARY}')),
    (display_cmake, ('set(DISPLAY_PLUGINS_GL_LIBRARY gl)', 'set(DISPLAY_PLUGINS_GL_LIBRARY "")', '${DISPLAY_PLUGINS_GL_LIBRARY}')),
):
    for anchor in anchors:
        if anchor not in text:
            raise SystemExit(f"gated direct GL link contract missing {anchor!r}")
for token in ("QOpenGLFramebufferObject", "GLsync"):
    if token not in gl_ui_source:
        raise SystemExit(f"non-iOS compatibility evidence missing {token}")

print("iOS Vulkan platform backend valid: gpu-vk/vk only; both direct GL links gated")
