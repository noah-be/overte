#!/usr/bin/env python3
"""Source proof for removing Interface's direct iOS Vulkan gl link."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CMAKE = (ROOT / "interface/CMakeLists.txt").read_text()
GRAPHICS = (ROOT / "interface/src/Application_Graphics.cpp").read_text()
VK_CMAKE = (ROOT / "libraries/vk/CMakeLists.txt").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


require("set(INTERFACE_GL_LIBRARY gl)" in CMAKE and 'set(INTERFACE_GL_LIBRARY "")' in CMAKE,
        "Interface GL library is not platform-gated")
require("${INTERFACE_GL_LIBRARY}" in CMAKE,
        "Interface does not consume its gated GL variable")
require("#if !defined(Q_OS_IOS)\n#include <gl/GLHelpers.h>\n#endif" in GRAPHICS,
        "iOS still parses direct GL helpers")
require("#if !defined(Q_OS_IOS)\nQ_GUI_EXPORT void qt_gl_set_global_share_context" in GRAPHICS,
        "iOS still declares Qt global GL share functions")
require("#if !defined(Q_OS_IOS)\n    glClearColor" in GRAPHICS,
        "legacy GL clear/swap is not iOS-excluded")
require("_primaryWidget->createContext(globalShareContext);" in GRAPHICS,
        "VKWidget compatibility context initialization was removed")
require("if (!_primaryWidget->makeCurrent())" in GRAPHICS and
        "    _primaryWidget->makeCurrent();" in GRAPHICS,
        "Vulkan current-context lifecycle was removed")
require("_graphicsEngine->initializeGPU(_primaryWidget);" in GRAPHICS,
        "Vulkan GPU initialization was removed")
require("link_hifi_libraries(shared shaders gl)" in VK_CMAKE,
        "vk target no longer owns the compatibility-context GL dependency")

print("Interface iOS GL link removal valid: direct calls gated; VK context/GPU lifecycle preserved")
