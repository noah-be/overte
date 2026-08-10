#!/usr/bin/env python3
"""Contract for the target-owned iOS OpenGL ES compatibility boundary."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TARGET_GLAD = (ROOT / "cmake/macros/TargetGlad.cmake").read_text()
CONFIG = (ROOT / "libraries/gl/src/gl/Config.cpp").read_text()
CONAN_RECIPE = (ROOT / "ios/conanfile.py").read_text()
AUTOSCRIBE = (ROOT / "cmake/macros/AutoScribeShader.cmake").read_text()
INTERFACE_CMAKE = (ROOT / "interface/CMakeLists.txt").read_text()
SCRIPT_CMAKE = (ROOT / "libraries/script-engine/CMakeLists.txt").read_text()
ARCHIVE = (ROOT / "interface/src/ArchiveDownloadInterface.cpp").read_text()


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
require('self.requires("glad/0.1.36@overte/experimental#' in CONAN_RECIPE,
        "the iOS graph does not provide the pinned glad package")
require('"glad*:gles2_version": "3.2"' in CONAN_RECIPE and
        '"glad*:gl_version": "4.5"' in CONAN_RECIPE,
        "the iOS glad package does not generate the required GL/GLES declarations")
require("if(IOS)\n            include(${CMAKE_BINARY_DIR}/conan/cmake/ConanToolsDirs.cmake)" in AUTOSCRIBE,
        "iOS shader generation does not consume its staged Conan tool paths")
require('self.requires("nvidia-texture-tools/2023.01@overte/stable#' in CONAN_RECIPE and
        'self.requires("etc2comp/cci.20170424")' in CONAN_RECIPE,
        "the iOS image graph lacks its compiled texture-processing packages")
require('self.requires("gifcreator/2016.11@overte/stable")' in CONAN_RECIPE,
        "animated snapshot code lacks its target package")
require("if(NOT IOS)\n  target_quazip()\nendif()" in INTERFACE_CMAKE and
        "if (NOT ANDROID AND NOT IOS)\n  target_quazip()" in SCRIPT_CMAKE,
        "the Qt 5 QuaZIP package remains reachable from iOS")
require("#if defined(Q_OS_IOS)\n    Q_UNUSED(path)" in ARCHIVE and
        "Archive extraction is unavailable on iOS" in ARCHIVE,
        "the iOS archive API does not fail closed without QuaZIP")

print("iOS GL compatibility valid: OpenGLES+glad owned without desktop FindOpenGL")
