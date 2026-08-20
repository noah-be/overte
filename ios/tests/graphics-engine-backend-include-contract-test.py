#!/usr/bin/env python3
"""Source contract for backend-specific GraphicsEngine includes."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HEADER = (ROOT / "interface/src/graphics/GraphicsEngine.h").read_text()
SOURCE = (ROOT / "interface/src/graphics/GraphicsEngine.cpp").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


require("#include <gl/OffscreenGLCanvas.h>" not in HEADER,
        "GraphicsEngine must not expose its unused OffscreenGLCanvas dependency")
require("#ifdef USE_GL\n#include <gl/GLWidget.h>\n#else\n#include <vk/VKWidget.h>\n#endif" in HEADER,
        "GraphicsEngine widget selection must remain backend-specific")
require("#ifdef USE_GL\n#include <gpu/gl/GLBackend.h>\n#else\n#include <gpu/vk/VKBackend.h>\n#endif" in SOURCE,
        "GraphicsEngine backend headers must follow USE_GL")
require("gpu::Context::init<gpu::gl::GLBackend>();" in SOURCE,
        "OpenGL initialization must remain available")
require("gpu::Context::init<gpu::vk::VKBackend>();" in SOURCE,
        "Vulkan initialization must remain available")
require(SOURCE.count("primaryWidget->makeCurrent();") == 2,
        "GraphicsEngine context-current lifecycle changed unexpectedly")
require("#if !defined(Q_OS_ANDROID) && !defined(Q_OS_IOS)" in HEADER and
        "std::atomic<bool> _programsCompiled { true };" in HEADER,
        "iOS can again remain trapped on the startup shader splash")

print("GraphicsEngine backend includes valid: unused Offscreen GL removed; GL/VK selection preserved")
