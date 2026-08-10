#!/usr/bin/env python3
"""Contract for the target-owned iOS OpenGL ES compatibility boundary."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET_GLAD = (ROOT / "cmake/macros/TargetGlad.cmake").read_text()
CONFIG = (ROOT / "libraries/gl/src/gl/Config.cpp").read_text()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


ios_branch, remainder = TARGET_GLAD.split("elseif (ANDROID)", 1)
require("if (IOS)" in ios_branch, "TargetGlad lacks an iOS-specific branch")
require("find_package(OpenGL" not in ios_branch,
        "iOS compatibility targets still request desktop OpenGL")
require("find_package(glad QUIET REQUIRED)" in ios_branch,
        "iOS compatibility targets lost glad dispatch")
require("find_library(OVERTE_IOS_OPENGLES_FRAMEWORK OpenGLES REQUIRED)" in ios_branch,
        "iOS compatibility targets do not fail closed on OpenGLES")
require('"${OVERTE_IOS_OPENGLES_FRAMEWORK}"' in ios_branch,
        "the discovered iOS OpenGLES framework is not linked")
require("find_package(OpenGL QUIET REQUIRED)" in remainder and
        "OpenGL::GL glad::glad" in remainder,
        "desktop OpenGL/glad behavior was not preserved")
require("#elif defined(Q_OS_IOS)\n#include <QtGui/QOpenGLContext>" in CONFIG,
        "iOS GL dispatch lacks the Qt context API")
require("QOpenGLContext::currentContext()" in CONFIG and
        "context->getProcAddress(namez)" in CONFIG,
        "iOS GL dispatch is not sourced from its current Qt context")
require("#if defined(Q_OS_IOS)\n        gladLoadGLES2Loader(getGlProcessAddress);" in CONFIG,
        "iOS compatibility dispatch does not select the GLES loader")
require(CONFIG.count("#elif defined(Q_OS_IOS)") >= 4,
        "iOS GL loading/swap paths can still fall into desktop CGL branches")

print("iOS GL compatibility valid: OpenGLES+glad owned without desktop FindOpenGL")
