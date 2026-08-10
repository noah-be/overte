# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

# Keep the existing desktop and Android builds on Qt 5 while allowing new
# platform targets to opt into Qt 6 from one central switch.
if(NOT DEFINED OVERTE_QT_MAJOR)
    if(CMAKE_SYSTEM_NAME STREQUAL "iOS")
        set(_overte_default_qt_major 6)
    else()
        set(_overte_default_qt_major 5)
    endif()
    set(OVERTE_QT_MAJOR "${_overte_default_qt_major}" CACHE STRING
        "Qt major version used by Overte (5 or 6)")
endif()

set_property(CACHE OVERTE_QT_MAJOR PROPERTY STRINGS 5 6)
if(NOT OVERTE_QT_MAJOR MATCHES "^[56]$")
    message(FATAL_ERROR "OVERTE_QT_MAJOR must be 5 or 6, got '${OVERTE_QT_MAJOR}'")
endif()

set(OVERTE_QT_PACKAGE "Qt${OVERTE_QT_MAJOR}")
set(OVERTE_QT_TARGET_PREFIX "Qt${OVERTE_QT_MAJOR}::")

function(overte_find_qt)
    find_package(${OVERTE_QT_PACKAGE} ${ARGN})
endfunction()

function(overte_link_qt_modules target)
    foreach(_overte_qt_module IN ITEMS ${ARGN})
        target_link_libraries(${target} "${OVERTE_QT_TARGET_PREFIX}${_overte_qt_module}")
    endforeach()
endfunction()

function(overte_qt_add_binary_resources target input_file)
    if(OVERTE_QT_MAJOR EQUAL 6)
        qt_add_binary_resources(${target} "${input_file}" ${ARGN})
    else()
        qt5_add_binary_resources(${target} "${input_file}" ${ARGN})
    endif()
endfunction()

function(overte_qt_add_resources output_variable)
    if(OVERTE_QT_MAJOR EQUAL 6)
        qt_add_resources(${output_variable} ${ARGN})
    else()
        qt5_add_resources(${output_variable} ${ARGN})
    endif()
    set(${output_variable} "${${output_variable}}" PARENT_SCOPE)
endfunction()

function(overte_qt_wrap_ui output_variable)
    if(OVERTE_QT_MAJOR EQUAL 6)
        qt_wrap_ui(${output_variable} ${ARGN})
    else()
        qt5_wrap_ui(${output_variable} ${ARGN})
    endif()
    set(${output_variable} "${${output_variable}}" PARENT_SCOPE)
endfunction()
