#!/usr/bin/env python3
"""Contract for the backend-neutral public Quick texture-copy ABI."""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
public_header = (ROOT / "libraries/plugins/src/plugins/DisplayPlugin.h").read_text(encoding="utf-8")
for forbidden in ("QOpenGLFramebufferObject", "GLsync"):
    if forbidden in public_header:
        raise SystemExit(f"public display plugin ABI still exposes {forbidden}")
for required in ("struct QuickTextureCopyTarget", "void* framebuffer", "void** completionToken", "virtual bool copyTextureToQuickFramebuffer"):
    if required not in public_header:
        raise SystemExit(f"public Quick-copy ABI missing {required!r}")

vulkan = (ROOT / "libraries/display-plugins/src/display-plugins/VulkanDisplayPlugin.cpp").read_text(encoding="utf-8")
ios_gate = vulkan.index("#if defined(OVERTE_IOS_VULKAN_DISABLE_QUICK_GL_COPY)", vulkan.index("copyTextureToQuickFramebuffer"))
fallback = vulkan.index("#else", ios_gate)
ios_branch = vulkan[ios_gate:fallback]
for required in ("*quickTarget.completionToken = nullptr", "return false"):
    if required not in ios_branch:
        raise SystemExit(f"iOS Quick-copy ABI does not fail closed: missing {required!r}")
if "QOpenGLFramebufferObject" in ios_branch or "GLsync" in ios_branch:
    raise SystemExit("iOS Quick-copy branch still uses GL-specific types")

opengl = (ROOT / "libraries/display-plugins/src/display-plugins/OpenGLDisplayPlugin.cpp").read_text(encoding="utf-8")
for required in ("static_cast<QOpenGLFramebufferObject*>", "glFenceSync", "return true"):
    if required not in opengl:
        raise SystemExit(f"existing OpenGL implementation adapter missing {required!r}")

print("Quick texture-copy ABI valid: public contract neutral; iOS fails closed; OpenGL adapted")
