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

# Qt 6 does not ship XmlPatterns, and its iOS distribution does not expose the
# desktop OpenGL module. Keep this policy here so individual libraries cannot
# accidentally reintroduce unavailable package components.
set(OVERTE_QT_UNAVAILABLE_COMPONENTS "")
if(OVERTE_QT_MAJOR EQUAL 5)
    # Core5Compat only exists as a separate module in Qt 6. The same APIs are
    # part of QtCore in Qt 5, so explicit migration opt-ins must be ignored.
    list(APPEND OVERTE_QT_UNAVAILABLE_COMPONENTS Core5Compat)
endif()
if(CMAKE_SYSTEM_NAME STREQUAL "iOS" AND OVERTE_QT_MAJOR EQUAL 6)
    list(APPEND OVERTE_QT_UNAVAILABLE_COMPONENTS OpenGL XmlPatterns)
endif()

function(overte_filter_qt_components output_variable)
    set(_overte_qt_components ${ARGN})
    foreach(_overte_unavailable IN LISTS OVERTE_QT_UNAVAILABLE_COMPONENTS)
        list(REMOVE_ITEM _overte_qt_components "${_overte_unavailable}")
    endforeach()
    set(${output_variable} "${_overte_qt_components}" PARENT_SCOPE)
endfunction()

function(overte_find_qt)
    overte_filter_qt_components(_overte_find_arguments ${ARGN})
    find_package(${OVERTE_QT_PACKAGE} ${_overte_find_arguments})
endfunction()

function(overte_link_qt_modules target)
    overte_filter_qt_components(_overte_link_modules ${ARGN})
    foreach(_overte_qt_module IN LISTS _overte_link_modules)
        target_link_libraries(${target} "${OVERTE_QT_TARGET_PREFIX}${_overte_qt_module}")
    endforeach()
endfunction()

function(overte_get_qt_target output_variable component)
    set(_overte_qt_target "${OVERTE_QT_TARGET_PREFIX}${component}")
    if(NOT TARGET "${_overte_qt_target}")
        message(FATAL_ERROR "Required Qt target '${_overte_qt_target}' is unavailable")
    endif()
    set(${output_variable} "${_overte_qt_target}" PARENT_SCOPE)
endfunction()

function(overte_qt_add_binary_resources target input_file)
    if(OVERTE_QT_MAJOR EQUAL 6)
        qt6_add_binary_resources(${target} "${input_file}" ${ARGN})
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

function(overte_qt_add_translation output_variable)
    if(OVERTE_QT_MAJOR EQUAL 6)
        qt_add_translation(${output_variable} ${ARGN})
    else()
        qt5_add_translation(${output_variable} ${ARGN})
    endif()
    set(${output_variable} "${${output_variable}}" PARENT_SCOPE)
endfunction()
