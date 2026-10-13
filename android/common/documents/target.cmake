# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
function(overte_target_documents target)
    target_sources(${target} PRIVATE "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/src/NativeDocumentPicker.cpp")
    target_include_directories(${target} PRIVATE "${CMAKE_SOURCE_DIR}/libraries/ui/src")
    target_link_libraries(${target} PRIVATE ui Qt5::Core)
endfunction()
