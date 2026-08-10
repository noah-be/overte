#!/usr/bin/env python3
"""Source contract for the iOS Vulkan Qt Quick GL-copy boundary."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
cmake = (ROOT / "libraries/display-plugins/CMakeLists.txt").read_text(encoding="utf-8")
source = (ROOT / "libraries/display-plugins/src/display-plugins/VulkanDisplayPlugin.cpp").read_text(encoding="utf-8")
macro = "OVERTE_IOS_VULKAN_DISABLE_QUICK_GL_COPY"

ios_guard = cmake.index('if(IOS AND OVERTE_RENDERING_BACKEND STREQUAL "Vulkan")')
other_platforms = cmake.index("else()", ios_guard)
if f"{macro}=1" not in cmake[ios_guard:other_platforms]:
    raise SystemExit("iOS Vulkan display target does not enable the Quick-copy gate")

method = source.index("bool VulkanDisplayPlugin::copyTextureToQuickFramebuffer")
gate = source.index(f"#if defined({macro})", method)
fallback = source.index("#else", gate)
end = source.index("#endif", fallback)
ios_branch = source[gate:fallback]
for token in ("Q_UNUSED(networkTexture)", "Q_UNUSED(quickTarget.framebuffer)", "*quickTarget.completionToken = nullptr", "return false", "QRhi/Metal-native bridge is required"):
    if token not in ios_branch:
        raise SystemExit(f"Quick-copy gate missing {token!r}")
if "glFenceSync" in ios_branch or "glBindFramebuffer" in ios_branch:
    raise SystemExit("iOS Quick-copy gate must not issue GL commands")
if "#if 0" not in source[fallback:]:
    raise SystemExit("existing non-iOS Vulkan stub was not preserved")

print("iOS Vulkan Quick-copy gate valid: no GL commands; opaque token cleared")
