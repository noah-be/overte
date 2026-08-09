# 
#  Copyright 2018 High Fidelity, Inc.
#  Created by Gabriel Calero & Cristian Duarte on 2018/03/13
#
#  Distributed under the Apache License, Version 2.0.
#  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
# 
macro(TARGET_BREAKPAD)
    if (ANDROID AND USE_BREAKPAD)
        set(INSTALL_DIR ${HIFI_ANDROID_PRECOMPILED}/breakpad)
        set(BREAKPAD_INCLUDE_DIRS "${INSTALL_DIR}/include" CACHE STRING INTERNAL)
        set(LIB_DIR ${INSTALL_DIR}/lib)
        list(APPEND BREAKPAD_LIBRARIES ${LIB_DIR}/libbreakpad_client.a)
        target_include_directories(${TARGET_NAME} SYSTEM PRIVATE ${BREAKPAD_INCLUDE_DIRS})
        add_definitions(-DHAS_BREAKPAD)
        target_link_libraries(${TARGET_NAME} ${BREAKPAD_LIBRARIES})
    endif()
endmacro()

