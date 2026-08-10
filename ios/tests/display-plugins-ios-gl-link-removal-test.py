#!/usr/bin/env python3
"""Source proof for removing display-plugins' direct iOS Vulkan gl link."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CMAKE = (ROOT / "libraries/display-plugins/CMakeLists.txt").read_text()
VULKAN = (ROOT / "libraries/display-plugins/src/display-plugins/VulkanDisplayPlugin.cpp").read_text()
COMPOSITOR = (ROOT / "libraries/display-plugins/src/display-plugins/CompositorHelper.cpp").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


require('set(DISPLAY_PLUGINS_GL_LIBRARY gl)' in CMAKE,
        "non-iOS direct GL dependency changed")
require('if(IOS AND OVERTE_RENDERING_BACKEND STREQUAL "Vulkan")' in CMAKE and
        'set(DISPLAY_PLUGINS_GL_LIBRARY "")' in CMAKE,
        "iOS Vulkan must clear the direct GL dependency")
require("${DISPLAY_PLUGINS_GL_LIBRARY}" in CMAKE,
        "gated GL variable is not used by the link list")
require("#include <gl/GLWidget.h>" not in COMPOSITOR,
        "CompositorHelper retains an unused GL widget include")
require("#if !defined(OVERTE_IOS_VULKAN_DISABLE_QUICK_GL_COPY)\n#include <gl/Config.h>\n#endif" in VULKAN,
        "raw GL configuration header is not behind the iOS Quick-copy gate")

for include in (
    "#include <QtGui/QOpenGLFramebufferObject>",
    "#include <gl/Context.h>",
    "#include <gl/OffscreenGLCanvas.h>",
    "#include <gpu/gl/GLTexelFormat.h>",
):
    position = VULKAN.index(include)
    prefix = VULKAN[max(0, position - 100):position]
    require("#if !defined(" in prefix,
            f"{include} is not compile-gated for iOS")

print("display-plugins iOS GL link removal valid: remaining Vulkan GL includes are gated")
