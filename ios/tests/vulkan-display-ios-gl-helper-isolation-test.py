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
require("#if !defined(Q_OS_IOS)\n#include <gl/Context.h>\n#include <gl/OffscreenGLCanvas.h>\n#endif" in SOURCE,
        "GL memory/context helper includes must be excluded on iOS")
require("#if !defined(OVERTE_IOS_VULKAN_DISABLE_QUICK_GL_COPY)\n#include <QtGui/QOpenGLFramebufferObject>\n#endif" in SOURCE,
        "disabled iOS Quick-copy must not parse the GL FBO type")
require("#if defined(Q_OS_IOS)\n        gpu::Backend::freeGPUMemSize.set(0);\n#else" in SOURCE,
        "iOS must not report a GL driver's memory as Metal memory")

# KTX1 capture is retained for non-iOS, but neither mapping nor header is parsed on iOS.
require("#if !defined(Q_OS_IOS)\n#include <gpu/gl/GLTexelFormat.h>\n#endif" in SOURCE,
        "GLTexelFormat header must be excluded on iOS")
require("KTX1 requires the legacy GL format mapping" in SOURCE,
        "iOS KTX capture must fail closed with its source-level reason")
require("#if !defined(Q_OS_IOS)\n    if (!OffscreenGLCanvas::restoreThreadContext())" in SOURCE,
        "legacy context restore must be excluded on iOS and preserved elsewhere")
require(SOURCE.count("#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)") == 4,
        "macOS present-thread GL current/swap calls must not compile for iOS")
require("#if !defined(Q_OS_IOS)\n        if (!widget->context()->makeCurrent())" in SOURCE,
        "display activation must not access the absent iOS GL context")
require("#if !defined(Q_OS_IOS)\n            auto context = _container->getPrimaryWidget()->context();" in SOURCE,
        "Vulkan execution must retain desktop GL ownership without requiring it on iOS")
swap_body = SOURCE.split("void VulkanDisplayPlugin::swapBuffers() {", 1)[1].split("\n}", 1)[0]
require(swap_body.lstrip().startswith("#if !defined(Q_OS_IOS)"),
        "legacy widget swap must compile out on iOS")

print("Vulkan display GL helper isolation valid: iOS memory/FBO/KTX/context-restore helpers excluded")
