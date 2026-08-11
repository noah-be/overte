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
require("Unsupported,\n            OpenGL," in HEADER,
        "context descriptor must not claim an unimplemented QRhi backend")
require("context.backend != SharedGraphicsContext::Backend::OpenGL || !context.handle" in SOURCE,
        "unsupported/null leases must fail closed")
require("setSharedContext(static_cast<QOpenGLContext*>(context.handle));" in SOURCE,
        "existing desktop OpenGL implementation is not adapted")
require("#if !defined(Q_OS_IOS)\n#include <QtGui/QSurfaceFormat>\n#endif" in GRAPHICS,
        "desktop surface-format calls must include their concrete Qt type without exposing it to iOS")
require("#if !defined(Q_OS_IOS)\n#include <gl/GLHelpers.h>\n#include <gl/OffscreenGLCanvas.h>\n#endif" in GRAPHICS,
        "desktop OffscreenGLCanvas users must include their concrete type without exposing it to iOS")
require("#if defined(Q_OS_IOS)\n    const hifi::qml::OffscreenSurface::SharedGraphicsContext" in GRAPHICS,
        "iOS does not use the backend-neutral contract")
require("Backend::Unsupported" in GRAPHICS and "native QRhi context lease is implemented" in GRAPHICS,
        "iOS must explicitly report its unsupported context lease")
require("#else\n    {\n        OffscreenGLCanvas* qmlShareContext" in GRAPHICS,
        "non-iOS GL QML producer changed unexpectedly")
require("OffscreenQmlSurface::setSharedContext(qmlShareContext->getContext());" in GRAPHICS,
        "existing desktop GL sharing behavior changed")

print("Offscreen QML context contract valid: desktop GL adapted; iOS fails closed without fake QRhi")
