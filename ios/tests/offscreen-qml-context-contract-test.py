#!/usr/bin/env python3
"""Contract for the backend-neutral Offscreen QML context boundary."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HEADER = (ROOT / "libraries/qml/src/qml/OffscreenSurface.h").read_text()
SOURCE = (ROOT / "libraries/qml/src/qml/OffscreenSurface.cpp").read_text()
GRAPHICS = (ROOT / "interface/src/Application_Graphics.cpp").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


require("struct SharedGraphicsContext" in HEADER and "void* handle { nullptr };" in HEADER,
        "backend-neutral context descriptor is missing")
require("Unsupported,\n            OpenGL,\n            Software," in HEADER,
        "context descriptor does not expose the software compatibility backend")
require("bool fetchImage(QImage& image);" in HEADER,
        "software-rendered Qt Quick frames cannot cross the surface boundary")
require("context.backend == SharedGraphicsContext::Backend::Software" in SOURCE and
        "SharedObject::setSoftwareRendering();" in SOURCE,
        "software context lease is not configured")
require("context.backend != SharedGraphicsContext::Backend::OpenGL || !context.handle" in SOURCE,
        "unsupported/null leases must fail closed")
require("setSharedContext(static_cast<QOpenGLContext*>(context.handle));" in SOURCE,
        "existing desktop OpenGL implementation is not adapted")
require("#if defined(Q_OS_IOS)\n    const hifi::qml::OffscreenSurface::SharedGraphicsContext" in GRAPHICS,
        "iOS does not use the backend-neutral contract")
require("Backend::Software" in GRAPHICS and "backend=software transfer=cpu-vulkan" in GRAPHICS,
        "iOS does not select and report the CPU-to-Vulkan Qt Quick bridge")
require("#else\n    {\n        OffscreenGLCanvas* qmlShareContext" in GRAPHICS,
        "non-iOS GL QML producer changed unexpectedly")
require("OffscreenQmlSurface::setSharedContext(qmlShareContext->getContext());" in GRAPHICS,
        "existing desktop GL sharing behavior changed")

print("Offscreen QML context contract valid: desktop GL preserved; iOS software frames cross a backend-neutral boundary")
