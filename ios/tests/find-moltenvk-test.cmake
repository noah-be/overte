# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_LIST_DIR}/../../cmake/modules")
set(CMAKE_OSX_SYSROOT "/Applications/Xcode.app/Platforms/iPhoneSimulator.platform/iPhoneSimulator.sdk")
set(OVERTE_IOS_SDK_NAME iphonesimulator)
set(OVERTE_IOS_MOLTENVK_ROOT "/overte-test/missing-moltenvk")
find_package(MoltenVK QUIET)

if(NOT _moltenvk_slice STREQUAL "ios-arm64_x86_64-simulator")
    message(FATAL_ERROR "The explicit simulator SDK selected ${_moltenvk_slice}")
endif()

if(MoltenVK_FOUND)
    message(FATAL_ERROR "A missing MoltenVK distribution was accepted")
endif()

message(STATUS "MoltenVK lookup fails closed")
