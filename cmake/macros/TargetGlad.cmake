# 
#  Copyright 2015 High Fidelity, Inc.
#  Copyright 2026 Overte e.V.
#  Created by Bradley Austin Davis on 2015/10/10
#
#  Distributed under the Apache License, Version 2.0.
#  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
# 
macro(TARGET_GLAD)
    if (IOS)
        # FindOpenGL models desktop OpenGL and does not expose an iphoneos
        # target.  The remaining target-owned compatibility contexts use the
        # OpenGL ES framework while function dispatch continues through the
        # same Conan-provided glad target.
        find_package(glad QUIET REQUIRED)
        find_library(OVERTE_IOS_OPENGLES_FRAMEWORK OpenGLES REQUIRED)
        target_link_libraries(${TARGET_NAME}
            glad::glad
            "${OVERTE_IOS_OPENGLES_FRAMEWORK}")
    elseif (ANDROID)
        include(SelectLibraryConfigurations)
        set(INSTALL_DIR ${HIFI_ANDROID_PRECOMPILED}/glad)
        set(GLAD_INCLUDE_DIRS "${INSTALL_DIR}/include")
        set(GLAD_LIBRARY_DEBUG ${INSTALL_DIR}/lib/libglad_d.a)
        set(GLAD_LIBRARY_RELEASE ${INSTALL_DIR}/lib/libglad.a)
        select_library_configurations(GLAD)
        find_library(EGL EGL)
        target_link_libraries(${TARGET_NAME} ${EGL})
        target_link_libraries(${TARGET_NAME} OpenGL::GL glad::glad)
    else()
        find_package(OpenGL QUIET REQUIRED)
        find_package(glad QUIET REQUIRED)
        target_link_libraries(${TARGET_NAME} OpenGL::GL glad::glad)
    endif()
    # target_link_libraries(${TARGET_NAME} ${GLAD_EXTRA_LIBRARIES})       
endmacro()
