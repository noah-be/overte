# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.9)

get_filename_component(_source_root "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
include("${_source_root}/cmake/macros/FixupInterface.cmake")

set(_test_root "${CMAKE_CURRENT_BINARY_DIR}/macdeployqt-discovery-test")
file(REMOVE_RECURSE "${_test_root}")
file(MAKE_DIRECTORY
    "${_test_root}/qt5/bin"
    "${_test_root}/qt5/lib/cmake/Qt5Core"
    "${_test_root}/qt6/bin"
    "${_test_root}/qt6/lib/cmake/Qt6Core"
)
file(WRITE "${_test_root}/qt5/bin/macdeployqt" "qt5")
file(WRITE "${_test_root}/qt6/bin/macdeployqt" "qt6")
execute_process(COMMAND chmod +x
    "${_test_root}/qt5/bin/macdeployqt"
    "${_test_root}/qt6/bin/macdeployqt"
)

set(Qt5Core_DIR "${_test_root}/qt5/lib/cmake/Qt5Core")
set(Qt6Core_DIR "")
set(QT_DIR "")
set(QT_HOST_PATH "")
set(CMAKE_PREFIX_PATH "")
overte_find_macdeployqt(_qt5_macdeployqt)
if (NOT _qt5_macdeployqt STREQUAL "${_test_root}/qt5/bin/macdeployqt")
    message(FATAL_ERROR "Qt 5 package discovery returned '${_qt5_macdeployqt}'")
endif()

set(Qt5Core_DIR "")
set(Qt6Core_DIR "${_test_root}/qt6/lib/cmake/Qt6Core")
overte_find_macdeployqt(_qt6_macdeployqt)
if (NOT _qt6_macdeployqt STREQUAL "${_test_root}/qt6/bin/macdeployqt")
    message(FATAL_ERROR "Qt 6 package discovery returned '${_qt6_macdeployqt}'")
endif()

file(REMOVE_RECURSE "${_test_root}")
message(STATUS "macdeployqt discovery contract valid")
