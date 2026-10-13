# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
function(overte_target_embedded_web target)
    target_sources(${target} PRIVATE
        "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/src/NativeWebViewItem.cpp"
        "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/src/NativeWebViewItem.h"
        "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/embedded-web.qrc")
    target_include_directories(${target} PRIVATE "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/src"
        "${CMAKE_SOURCE_DIR}/libraries/shared/src")
    target_link_libraries(${target} PRIVATE Qt5::Quick Qt5::WebChannel Qt5::Network)
endfunction()
