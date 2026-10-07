# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.24)

set(OVERTE_QT_MAJOR 5 CACHE STRING "Qt major for compatibility fixture" FORCE)
set(CMAKE_SYSTEM_NAME Linux)
include("${CMAKE_CURRENT_LIST_DIR}/../../cmake/QtCompat.cmake")

if(NOT OVERTE_QT_PACKAGE STREQUAL "Qt5" OR NOT OVERTE_QT_TARGET_PREFIX STREQUAL "Qt5::")
    message(FATAL_ERROR "Qt 5 fixture selected the wrong package or target prefix")
endif()

overte_filter_qt_components(
    FILTERED_QT5_COMPONENTS
    COMPONENTS Core Gui Core5Compat REQUIRED
)
if("Core5Compat" IN_LIST FILTERED_QT5_COMPONENTS)
    message(FATAL_ERROR "Qt 5 filtering retained the nonexistent Core5Compat component")
endif()
foreach(REQUIRED_ITEM COMPONENTS Core Gui REQUIRED)
    if(NOT REQUIRED_ITEM IN_LIST FILTERED_QT5_COMPONENTS)
        message(FATAL_ERROR "Qt 5 component filtering removed ${REQUIRED_ITEM}")
    endif()
endforeach()

# Qt 5 rejects find_package(Qt5 COMPONENTS) without a remaining component.
# Exercise the wrapper against that package contract without a host Qt install.
set_property(GLOBAL PROPERTY OVERTE_QT5_FIND_CALLS 0)
function(find_package package)
    if(NOT package STREQUAL "Qt5")
        message(FATAL_ERROR "Qt 5 wrapper requested ${package}")
    endif()
    cmake_parse_arguments(REQUEST "QUIET;REQUIRED" "" "COMPONENTS;OPTIONAL_COMPONENTS" ${ARGN})
    if(NOT REQUEST_COMPONENTS AND NOT REQUEST_OPTIONAL_COMPONENTS)
        message(FATAL_ERROR "The Qt5 package requires at least one component")
    endif()
    if("Core5Compat" IN_LIST REQUEST_COMPONENTS OR "Core5Compat" IN_LIST REQUEST_OPTIONAL_COMPONENTS)
        message(FATAL_ERROR "Qt 5 wrapper requested the nonexistent Core5Compat module")
    endif()
    get_property(CALLS GLOBAL PROPERTY OVERTE_QT5_FIND_CALLS)
    math(EXPR CALLS "${CALLS} + 1")
    set_property(GLOBAL PROPERTY OVERTE_QT5_FIND_CALLS "${CALLS}")
    set_property(GLOBAL PROPERTY OVERTE_QT5_FIND_COMPONENTS "${REQUEST_COMPONENTS}")
    if(NOT REQUEST_REQUIRED OR NOT REQUEST_QUIET)
        message(FATAL_ERROR "Qt 5 wrapper lost its requested package flags")
    endif()
endfunction()

overte_find_qt(COMPONENTS Core5Compat QUIET REQUIRED)
overte_find_qt(OPTIONAL_COMPONENTS Core5Compat QUIET REQUIRED)
get_property(CALLS GLOBAL PROPERTY OVERTE_QT5_FIND_CALLS)
if(NOT CALLS EQUAL 0)
    message(FATAL_ERROR "Core5Compat-only requests must not discover an empty Qt 5 package")
endif()

overte_find_qt(COMPONENTS Core Core5Compat Gui QUIET REQUIRED)
get_property(CALLS GLOBAL PROPERTY OVERTE_QT5_FIND_CALLS)
get_property(COMPONENTS GLOBAL PROPERTY OVERTE_QT5_FIND_COMPONENTS)
if(NOT CALLS EQUAL 1 OR NOT COMPONENTS STREQUAL "Core;Gui")
    message(FATAL_ERROR "Qt 5 wrapper did not discover the remaining requested modules")
endif()

message(STATUS "Qt 5 compatibility contract passed")
