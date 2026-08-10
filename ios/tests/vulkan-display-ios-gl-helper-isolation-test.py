#!/usr/bin/env python3
"""Contract for the remaining VulkanDisplayPlugin GL helper boundary."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "libraries/display-plugins/src/display-plugins/VulkanDisplayPlugin.cpp").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


require("#include <gl/QOpenGLContextWrapper.h>" not in SOURCE,
        "unused QOpenGLContextWrapper include remains")
require("#include <gl/GLEscrow.h>" not in SOURCE,
        "unused GLEscrow include remains")
require("#if !defined(Q_OS_IOS)\n#include <gl/Context.h>\n#endif" in SOURCE,
        "GL memory helper include must be excluded on iOS")
require("#if !defined(OVERTE_IOS_VULKAN_DISABLE_QUICK_GL_COPY)\n#include <QtGui/QOpenGLFramebufferObject>\n#endif" in SOURCE,
        "disabled iOS Quick-copy must not parse the GL FBO type")
require("#if defined(Q_OS_IOS)\n        gpu::Backend::freeGPUMemSize.set(0);\n#else" in SOURCE,
        "iOS must not report a GL driver's memory as Metal memory")

# These two dependencies remain real and may only move with their producer contracts.
require("gpu::gl::GLTexelFormat::evalGLTexelFormat" in SOURCE,
        "KTX capture format dependency moved; update this audit")
require("OffscreenGLCanvas::restoreThreadContext()" in SOURCE,
        "QML context restore moved; update the native-RHI migration audit")

print("Vulkan display GL helper isolation valid: iOS memory/FBO helpers excluded; two real contracts remain")
