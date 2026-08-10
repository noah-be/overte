#!/usr/bin/env python3
"""Audit the current Offscreen QML backend and the safe iOS WebEngine slice."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INTERFACE_CMAKE = (ROOT / "interface/CMakeLists.txt").read_text()
GRAPHICS = (ROOT / "interface/src/Application_Graphics.cpp").read_text()
SURFACE = (ROOT / "libraries/qml/src/qml/OffscreenSurface.h").read_text()
SHARED = (ROOT / "libraries/qml/src/qml/impl/SharedObject.h").read_text()
RENDER = (ROOT / "libraries/qml/src/qml/impl/RenderEventHandler.cpp").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


require("if(NOT IOS)\n  list(APPEND INTERFACE_QT_COMPONENTS WebEngineCore WebEngineWidgets)" in INTERFACE_CMAKE,
        "iOS WebEngine exclusion changed; Chromium GL slice needs re-audit")
require("#if !defined(DISABLE_QML) && !defined(Q_OS_IOS)\n    // Build a shared canvas / context for the Chromium processes" in GRAPHICS,
        "iOS must not create the absent Chromium helper's GL share context")

# The remaining QML canvas is intentional until all three GL contracts migrate.
require("OffscreenGLCanvas* qmlShareContext" in GRAPHICS,
        "QML shared canvas changed without a native producer contract")
require("using TextureAndFence = std::pair<uint32_t, void*>;" in SURFACE,
        "Offscreen texture ABI changed; update the QRhi migration audit")
require("void initializeRenderControl(QOpenGLContext* context);" in SHARED,
        "Render-control context ABI changed; update the QRhi migration audit")
require("QOpenGLContextWrapper::currentContext()" in RENDER,
        "Render-thread GL context dependency changed; update the QRhi migration audit")

print("Offscreen QML backend audit valid: iOS Chromium context excluded; native QRhi migration remains gated")
