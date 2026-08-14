#!/usr/bin/env python3
"""Contract for excluding OpenGL display families from iOS Vulkan builds."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
cmake = (ROOT / "libraries/display-plugins/CMakeLists.txt").read_text(encoding="utf-8")
registration = (ROOT / "libraries/display-plugins/src/display-plugins/DisplayPlugin.cpp").read_text(encoding="utf-8")
application_plugins = (ROOT / "interface/src/Application_Plugins.cpp").read_text(encoding="utf-8")
vision_squeeze = (ROOT / "interface/src/VisionSqueeze.cpp").read_text(encoding="utf-8")
interface_menu = (ROOT / "interface/src/Menu.cpp").read_text(encoding="utf-8")

if "#include <display-plugins/CompositorHelper.h>" not in application_plugins:
    raise SystemExit("Application_Plugins.cpp must own the complete CompositorHelper type it calls")

start = cmake.index('if(IOS AND OVERTE_RENDERING_BACKEND STREQUAL "Vulkan")')
end = cmake.index("endif()", start)
branch = cmake[start:end]
expected = {
    "Basic2DWindowOpenGLDisplayPlugin.cpp", "Basic2DWindowOpenGLDisplayPlugin.h",
    "OpenGLDisplayPlugin.cpp", "OpenGLDisplayPlugin.h",
    "DebugHmdDisplayPlugin.cpp", "DebugHmdDisplayPlugin.h",
    "HmdDisplayPlugin.cpp", "HmdDisplayPlugin.h",
    "InterleavedStereoDisplayPlugin.cpp", "InterleavedStereoDisplayPlugin.h",
    "SideBySideStereoDisplayPlugin.cpp", "SideBySideStereoDisplayPlugin.h",
    "StereoDisplayPlugin.cpp", "StereoDisplayPlugin.h",
}
listed = set(re.findall(r"(?:^|/)([A-Za-z0-9]+(?:DisplayPlugin)\.(?:cpp|h))", branch))
if listed != expected:
    raise SystemExit(f"unexpected iOS OpenGL display exclusion list: missing={expected-listed}, extra={listed-expected}")
for token in ("HEADER_FILE_ONLY TRUE", "SKIP_AUTOMOC TRUE"):
    if token not in branch:
        raise SystemExit(f"iOS source exclusion missing {token!r}")

for token in ('#include "hmd/DebugHmdDisplayPlugin.h"', "new DebugHmdDisplayPlugin()"):
    position = registration.index(token)
    guard = registration.rfind("#if !defined(Q_OS_IOS)", 0, position)
    close = registration.find("#endif", position)
    if guard < 0 or close < 0 or registration.find("#endif", guard, position) >= 0:
        raise SystemExit(f"iOS plugin registration does not guard {token!r}")

for source, tokens in (
    (application_plugins, (
        "#include <display-plugins/hmd/HmdDisplayPlugin.h>",
        "dynamic_cast<HmdDisplayPlugin*>",
        "&HmdDisplayPlugin::hmdMountedChanged",
        "&HmdDisplayPlugin::hmdVisibleChanged",
    )),
    (vision_squeeze, (
        "#include <display-plugins/hmd/HmdDisplayPlugin.h>",
        "std::dynamic_pointer_cast<HmdDisplayPlugin>",
        "hmdDisplayPlugin->updateVisionSqueezeParameters",
    )),
    (interface_menu, (
        "#include <display-plugins/OpenGLDisplayPlugin.h>",
        "OpenGLDisplayPlugin::getExtraLinearToSRGBConversion",
        "OpenGLDisplayPlugin::setExtraLinearToSRGBConversion",
    )),
):
    for token in tokens:
        position = source.index(token)
        guard = source.rfind("#if !defined(Q_OS_IOS)", 0, position)
        close = source.find("#endif", position)
        if guard < 0 or close < 0 or source.find("#endif", guard, position) >= 0:
            raise SystemExit(f"iOS Interface consumer does not guard excluded display symbol {token!r}")

print("iOS display source isolation valid: 14 OpenGL/stereo/HMD files excluded; compositor complete; registration and consumers guarded")
