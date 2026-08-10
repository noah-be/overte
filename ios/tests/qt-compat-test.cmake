# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set(CMAKE_SYSTEM_NAME iOS)
include("${CMAKE_CURRENT_LIST_DIR}/../../cmake/QtCompat.cmake")

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

message(STATUS "Qt compatibility contract passed")
