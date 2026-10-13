# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
function(overte_target_snapshot target)
    target_sources(${target} PRIVATE
        "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/src/NativeSnapshotAdapter.cpp"
        "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/src/NativeSnapshotAdapter.h")
    target_include_directories(${target} PRIVATE "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/src"
        "${CMAKE_SOURCE_DIR}/interface/src/ui")
    target_link_libraries(${target} PRIVATE Qt5::Core Qt5::Qml)
endfunction()
