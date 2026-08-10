#!/usr/bin/env python3
"""Contract for excluding OpenGL display families from iOS Vulkan builds."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
cmake = (ROOT / "libraries/display-plugins/CMakeLists.txt").read_text(encoding="utf-8")
registration = (ROOT / "libraries/display-plugins/src/display-plugins/DisplayPlugin.cpp").read_text(encoding="utf-8")

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

print("iOS display source isolation valid: 14 OpenGL/stereo/HMD files excluded; registration guarded")
