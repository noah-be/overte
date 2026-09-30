# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.24)
project(EmbeddedWebserverTests LANGUAGES CXX)
enable_testing()
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTOMOC ON)
get_filename_component(OVERTE_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
set(OVERTE_QT_MAJOR 6 CACHE STRING "Qt major version used by the Apple HTTP tests")
include("${OVERTE_ROOT}/cmake/QtCompat.cmake")
overte_find_qt(REQUIRED COMPONENTS Core Network Test)
file(GLOB PRODUCT_SOURCES "${OVERTE_ROOT}/libraries/embedded-webserver/src/*.cpp"
                          "${OVERTE_ROOT}/libraries/embedded-webserver/src/*.h")
add_library(embedded-webserver STATIC ${PRODUCT_SOURCES})
target_link_libraries(embedded-webserver PUBLIC ${OVERTE_QT_TARGET_PREFIX}Core ${OVERTE_QT_TARGET_PREFIX}Network)
target_include_directories(embedded-webserver PUBLIC "${OVERTE_ROOT}/libraries/embedded-webserver/src")
set(TEST_PROJ_NAME embedded-webserver)
include("${OVERTE_ROOT}/cmake/macros/SetupHifiTestCase.cmake")
# This library and its tests have no GLM dependency.
macro(target_glm)
endmacro()
set(OVERTE_WEBSERVER_STANDALONE ON)

add_subdirectory("${OVERTE_ROOT}/tests/embedded-webserver" embedded-webserver-tests)
