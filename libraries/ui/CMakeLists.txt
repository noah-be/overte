# Copyright 2013-2018, High Fidelity, Inc.
# Copyright 2020-2023 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set(TARGET_NAME ui)
set(UI_QT_COMPONENTS Multimedia Network Qml Quick WebChannel WebSockets)
if (NOT (IOS AND OVERTE_QT_MAJOR EQUAL 6))
  list(APPEND UI_QT_COMPONENTS OpenGL)
endif()
setup_hifi_library(${UI_QT_COMPONENTS} ${PLATFORM_QT_COMPONENTS})
link_hifi_libraries(shared networking qml gl audio audio-client plugins pointers script-engine)
include_hifi_library_headers(controllers)

# Required for some low level GL interaction in the OffscreenQMLSurface
set(OpenGL_GL_PREFERENCE "GLVND")
target_opengl()

if (WIN32)
  add_compile_definitions(_USE_MATH_DEFINES)
endif()
