#!/usr/bin/env python3
"""Contract for GL-free iOS telemetry and driver-blocklist behavior."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APPLICATION = (ROOT / "interface/src/Application.cpp").read_text()
SETUP = (ROOT / "interface/src/Application_Setup.cpp").read_text()
GRAPHICS = (ROOT / "interface/src/Application_Graphics.cpp").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


guarded_include = '#if !defined(Q_OS_IOS)\n#include <gl/GLHelpers.h>\n#endif'
require(guarded_include in APPLICATION, "Application GLHelpers include is not iOS-excluded")
require(guarded_include in SETUP, "Application_Setup GLHelpers include is not iOS-excluded")
require("#if !defined(ANDROID_APP_PHONE_INTERFACE) && !defined(Q_OS_IOS)" in APPLICATION,
        "desktop driver blocklist must be excluded on iOS")
require('#if defined(Q_OS_IOS)\n            { "graphics_backend"' in SETUP,
        "iOS session telemetry lacks backend-neutral GPU identity")
require('#if defined(Q_OS_IOS)\n        properties["gl_info"]' in SETUP,
        "iOS activity telemetry lacks its schema-stable backend branch")
require(SETUP.count("gl::ContextInfo::get()") == 2,
        "non-iOS GL telemetry changed unexpectedly")

# This task must not alter the active QML sharing/context path.
require("OffscreenGLCanvas* qmlShareContext" in GRAPHICS,
        "Offscreen QML sharing was altered")
require("_graphicsEngine->initializeGPU(_primaryWidget);" in GRAPHICS,
        "GPU initialization was altered")

print("iOS GL telemetry isolation valid: backend reported; desktop GL telemetry preserved")
