# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.24)

set(CMAKE_SYSTEM_NAME iOS)
include("${CMAKE_CURRENT_LIST_DIR}/../../cmake/QtCompat.cmake")

file(READ "${CMAKE_CURRENT_LIST_DIR}/../../cmake/QtCompat.cmake" QT_COMPAT_SOURCE)
if(NOT QT_COMPAT_SOURCE MATCHES "macro\\(overte_find_qt\\)")
    message(FATAL_ERROR "Qt package discovery must preserve package variables in the caller scope")
endif()

if(NOT OVERTE_QT_MAJOR STREQUAL "6")
    message(FATAL_ERROR "iOS did not select Qt 6")
endif()
if(NOT OVERTE_QT_PACKAGE STREQUAL "Qt6")
    message(FATAL_ERROR "iOS selected the wrong Qt package")
endif()
if(NOT OVERTE_QT_TARGET_PREFIX STREQUAL "Qt6::")
    message(FATAL_ERROR "iOS selected the wrong Qt target prefix")
endif()
if(NOT COMMAND overte_qt_add_resources)
    message(FATAL_ERROR "Qt resource compatibility helper is missing")
endif()

function(qt6_add_binary_resources target input_file)
    set(QT6_BINARY_RESOURCE_CALL "${target}|${input_file}|${ARGN}" CACHE INTERNAL "")
endfunction()
overte_qt_add_binary_resources(resources fixture.qrc DESTINATION fixture.rcc)
if(NOT QT6_BINARY_RESOURCE_CALL STREQUAL "resources|fixture.qrc|DESTINATION;fixture.rcc")
    message(FATAL_ERROR "Qt 6 binary resource dispatcher did not use explicit qt6 command: '${QT6_BINARY_RESOURCE_CALL}'")
endif()

overte_filter_qt_components(
    FILTERED_IOS_COMPONENTS
    COMPONENTS Core Gui OpenGL XmlPatterns WebView REQUIRED
)
if("OpenGL" IN_LIST FILTERED_IOS_COMPONENTS OR "XmlPatterns" IN_LIST FILTERED_IOS_COMPONENTS)
    message(FATAL_ERROR "unavailable Qt 6 iOS modules survived component filtering")
endif()
foreach(REQUIRED_ITEM COMPONENTS Core Gui WebView REQUIRED)
    if(NOT REQUIRED_ITEM IN_LIST FILTERED_IOS_COMPONENTS)
        message(FATAL_ERROR "Qt component filtering removed ${REQUIRED_ITEM}")
    endif()
endforeach()

set_property(GLOBAL PROPERTY OVERTE_QT6_FIND_CALLS 0)
function(find_package package)
    if(NOT package STREQUAL "Qt6")
        message(FATAL_ERROR "iOS wrapper requested ${package}")
    endif()
    cmake_parse_arguments(REQUEST "QUIET;REQUIRED" "" "COMPONENTS" ${ARGN})
    if(NOT REQUEST_COMPONENTS STREQUAL "Core5Compat" OR NOT REQUEST_REQUIRED OR NOT REQUEST_QUIET)
        message(FATAL_ERROR "Qt 6 Core5Compat discovery or its package flags were lost")
    endif()
    get_property(CALLS GLOBAL PROPERTY OVERTE_QT6_FIND_CALLS)
    math(EXPR CALLS "${CALLS} + 1")
    set_property(GLOBAL PROPERTY OVERTE_QT6_FIND_CALLS "${CALLS}")
    set(Qt6Core5Compat_FOUND TRUE PARENT_SCOPE)
endfunction()

overte_find_qt(COMPONENTS Core5Compat QUIET REQUIRED)
get_property(CALLS GLOBAL PROPERTY OVERTE_QT6_FIND_CALLS)
if(NOT CALLS EQUAL 1)
    message(FATAL_ERROR "Qt 6 must still discover its separate Core5Compat package")
endif()
if(NOT Qt6Core5Compat_FOUND)
    message(FATAL_ERROR "Qt 6 discovery did not expose its component variable to the caller")
endif()

message(STATUS "Qt compatibility contract passed")
