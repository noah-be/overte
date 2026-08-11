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

message(STATUS "Qt compatibility contract passed")
