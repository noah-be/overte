#!/usr/bin/env python3
"""Contract that iOS Vulkan does not compile or transitively include GLCanvas."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CMAKE = (ROOT / "interface/CMakeLists.txt").read_text()
USERS = [
    "Application.cpp",
    "Application_Graphics.cpp",
    "Application_UI.cpp",
    "Application_Events.cpp",
    "Application_Setup.cpp",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


require('if(IOS AND OVERTE_RENDERING_BACKEND STREQUAL "Vulkan")' in CMAKE,
        "GLCanvas exclusion must be scoped to iOS Vulkan")
for source in ("GLCanvas.cpp", "GLCanvas.h"):
    require(f'"${{CMAKE_CURRENT_SOURCE_DIR}}/src/{source}"' in CMAKE,
            f"iOS Vulkan source exclusion is missing {source}")

for name in USERS:
    text = (ROOT / "interface/src" / name).read_text()
    require('#ifdef USE_GL\n#include "GLCanvas.h"\n#endif' in text,
            f"{name} must not parse GLCanvas.h in a Vulkan build")

setup = (ROOT / "interface/src/Application_Setup.cpp").read_text()
require("#ifdef USE_GL\n    _primaryWidget = new GLCanvas();" in setup,
        "desktop/Android OpenGL GLCanvas construction changed")
require("#else\n    _primaryWidget = new VKCanvas();" in setup,
        "Vulkan VKCanvas construction changed")

graphics = (ROOT / "interface/src/Application_Graphics.cpp").read_text()
require("OffscreenGLCanvas* qmlShareContext" in graphics,
        "active QML shared-context creation was removed")
require("_graphicsEngine->initializeGPU(_primaryWidget);" in graphics,
        "central GPU initialization was removed")

print("iOS Vulkan GLCanvas isolation valid: legacy widget excluded; VK/QML/context paths preserved")
