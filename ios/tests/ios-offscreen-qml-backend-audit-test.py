#!/usr/bin/env python3
"""Audit the current Offscreen QML backend and the safe iOS WebEngine slice."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INTERFACE_CMAKE = (ROOT / "interface/CMakeLists.txt").read_text()
GRAPHICS = (ROOT / "interface/src/Application_Graphics.cpp").read_text()
SURFACE = (ROOT / "libraries/qml/src/qml/OffscreenSurface.h").read_text()
SHARED = (ROOT / "libraries/qml/src/qml/impl/SharedObject.h").read_text()
RENDER = (ROOT / "libraries/qml/src/qml/impl/RenderEventHandler.cpp").read_text()
SHARED_SOURCE = (ROOT / "libraries/qml/src/qml/impl/SharedObject.cpp").read_text()
WEB = (ROOT / "libraries/entities-renderer/src/RenderableWebEntityItem.cpp").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


require("if(NOT IOS)\n  list(APPEND INTERFACE_QT_COMPONENTS WebEngineCore WebEngineWidgets)" in INTERFACE_CMAKE,
        "iOS WebEngine exclusion changed; Chromium GL slice needs re-audit")
require("#if !defined(DISABLE_QML) && !defined(Q_OS_IOS)\n    // Build a shared canvas / context for the Chromium processes" in GRAPHICS,
        "iOS must not create the absent Chromium helper's GL share context")

# Desktop retains its OpenGL producer while iOS uses the Qt Quick software
# renderer. This avoids attempting to import a desktop GL texture into MoltenVK.
require("OffscreenGLCanvas* qmlShareContext" in GRAPHICS,
        "desktop QML shared canvas changed unexpectedly")
require("using TextureAndFence = std::pair<uint32_t, void*>;" in SURFACE,
        "desktop offscreen texture ABI changed unexpectedly")
require("void initializeRenderControl(QOpenGLContext* context);" in SHARED,
        "render-control compatibility ABI changed unexpectedly")
require("QOpenGLContextWrapper::currentContext()" in RENDER,
        "desktop render-thread GL path changed unexpectedly")
require("QQuickWindow::setGraphicsApi(QSGRendererInterface::Software)" in SHARED_SOURCE,
        "iOS software scene graph is not selected")
constructor = SHARED_SOURCE[SHARED_SOURCE.index("SharedObject::SharedObject()"):]
require(constructor.index("setSoftwareRendering();") < constructor.index("new QQuickWindow(_renderControl)"),
        "software scene graph must be selected before the first offscreen QQuickWindow")
require("QQuickRenderTarget::fromPaintDevice(&_softwareImage)" in RENDER,
        "software Qt Quick renderer has no QImage target")
require("_webSurface->fetchImage(newImage)" in WEB and
        'texture->setSource("WebEntityRendererSoftware")' in WEB,
        "software Qt Quick frames are not uploaded through a regular Vulkan texture")
require("OVERTE_IOS_QML_FRAME_GATE stage=cpu-frame-uploaded" in WEB,
        "device logs cannot prove that a QML frame reached Vulkan")

print("Offscreen QML backend audit valid: iOS Chromium excluded; Qt Quick software frames upload through ordinary Vulkan textures")
