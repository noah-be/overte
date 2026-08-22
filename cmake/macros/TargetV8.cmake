#
#  Copyright 2022-2026 Overte e.V.
#  Created by dr Karol Suprynowicz on 2022/09/03
#
#  Distributed under the Apache License, Version 2.0.
#  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
#  SPDX-License-Identifier: Apache-2.0
#
macro(TARGET_V8)
    if(IOS)
        set(OVERTE_IOS_V8_ROOT "$ENV{OVERTE_IOS_V8_ROOT}" CACHE PATH
            "Root of the audited static non-JIT V8/libnode iOS package")
        find_path(OVERTE_IOS_V8_INCLUDE_DIR v8.h
            HINTS "${OVERTE_IOS_V8_ROOT}/include/node"
            NO_DEFAULT_PATH)
        find_library(OVERTE_IOS_V8_LIBRARY
            NAMES node v8_monolith
            HINTS "${OVERTE_IOS_V8_ROOT}/lib"
            NO_DEFAULT_PATH)
        if(NOT OVERTE_IOS_V8_INCLUDE_DIR OR NOT OVERTE_IOS_V8_LIBRARY)
            message(FATAL_ERROR
                "iOS scripting requires an audited static non-JIT V8 package. "
                "Set OVERTE_IOS_V8_ROOT; see docs/ios/SCRIPTING.md.")
        endif()
        if(NOT OVERTE_IOS_V8_LIBRARY MATCHES "\\.a$")
            message(FATAL_ERROR
                "iOS scripting must link a static V8/libnode archive; found "
                "${OVERTE_IOS_V8_LIBRARY}")
        endif()
        target_compile_definitions(${TARGET_NAME} PRIVATE OVERTE_V8_JITLESS=1)
        target_include_directories(${TARGET_NAME} SYSTEM PRIVATE
            "${OVERTE_IOS_V8_INCLUDE_DIR}")
        target_link_libraries(${TARGET_NAME} "${OVERTE_IOS_V8_LIBRARY}")
    elseif(OVERTE_USE_SYSTEM_LIBS)
        # NOTE: this is configured for NixOS specifically
        find_package(PkgConfig REQUIRED)
        pkg_check_modules(libv8 REQUIRED v8)
        target_include_directories(${TARGET_NAME} SYSTEM PRIVATE ${libv8_INCLUDE_DIRS})
        target_link_libraries(${TARGET_NAME} ${libv8_LINK_LIBRARIES})
    else()
        find_package(libnode QUIET REQUIRED)
        target_link_libraries(${TARGET_NAME} libnode::libnode)
    endif()
endmacro()
