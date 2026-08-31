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

message(STATUS "Qt 5 compatibility contract passed")
