# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.24)

if(NOT CMAKE_SYSTEM_NAME STREQUAL "iOS")
    message(FATAL_ERROR "The iOS bootstrap target requires -DCMAKE_SYSTEM_NAME=iOS")
endif()

project(OverteIOSBootstrap VERSION 0.2.0 LANGUAGES C CXX OBJC OBJCXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(OVERTE_IOS_BUNDLE_IDENTIFIER "org.overte.bootstrap.dev" CACHE STRING
    "Bundle identifier for the iOS bootstrap application")
set(OVERTE_IOS_DEVELOPMENT_TEAM "" CACHE STRING
    "Apple Developer team ID; leave empty for unsigned simulator builds")
set(OVERTE_IOS_SDK_NAME "" CACHE STRING
    "Xcode SDK name used to compile Metal shaders")
option(OVERTE_IOS_ENABLE_SIGNING "Enable Xcode code signing" OFF)

if(NOT OVERTE_IOS_SDK_NAME MATCHES "^(iphoneos|iphonesimulator)$")
    message(FATAL_ERROR
        "OVERTE_IOS_SDK_NAME must be iphoneos or iphonesimulator")
endif()

set(OVERTE_IOS_RESOURCES
    resources/Assets.xcassets
    resources/PrivacyInfo.xcprivacy
)
if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/resources/PrivacyInfo.xcprivacy")
    message(FATAL_ERROR "The audited iOS PrivacyInfo.xcprivacy is required")
endif()

add_executable(OverteIOSBootstrap MACOSX_BUNDLE
    src/main.mm
    src/AppDelegate.h
    src/AppDelegate.mm
    src/SceneDelegate.h
    src/SceneDelegate.mm
    src/PlatformProbe.h
    src/PlatformProbe.mm
    src/PendingDeepLinkStore.h
    src/PendingDeepLinkStore.cpp
    src/OverteAddress.h
    src/OverteAddress.cpp
    src/LifecycleStateMachine.h
    src/LifecycleStateMachine.cpp
    src/BootstrapViewController.h
    src/BootstrapViewController.mm
    src/BootstrapShaders.metal
    ${OVERTE_IOS_RESOURCES}
)

set_source_files_properties(${OVERTE_IOS_RESOURCES} PROPERTIES
    MACOSX_PACKAGE_LOCATION Resources
)
set_source_files_properties(src/BootstrapShaders.metal PROPERTIES
    XCODE_EXPLICIT_FILE_TYPE "sourcecode.metal"
)

find_program(OVERTE_IOS_XCRUN xcrun REQUIRED)
set(OVERTE_IOS_METAL_TARGET "air64-apple-ios${CMAKE_OSX_DEPLOYMENT_TARGET}")
if(OVERTE_IOS_SDK_NAME STREQUAL "iphonesimulator")
    string(APPEND OVERTE_IOS_METAL_TARGET "-simulator")
endif()
set(OVERTE_IOS_METAL_OUTPUT_DIR "${CMAKE_CURRENT_BINARY_DIR}/metal/$<CONFIG>")
set(OVERTE_IOS_METAL_AIR "${OVERTE_IOS_METAL_OUTPUT_DIR}/BootstrapShaders.air")
set(OVERTE_IOS_METALLIB "${OVERTE_IOS_METAL_OUTPUT_DIR}/default.metallib")
set(OVERTE_IOS_APP_BUNDLE
    "${CMAKE_CURRENT_BINARY_DIR}/$<CONFIG>-${OVERTE_IOS_SDK_NAME}/OverteIOSBootstrap.app")

add_custom_command(TARGET OverteIOSBootstrap POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E make_directory "${OVERTE_IOS_METAL_OUTPUT_DIR}"
    COMMAND "${OVERTE_IOS_XCRUN}" --sdk "${OVERTE_IOS_SDK_NAME}" metal
        -c "${CMAKE_CURRENT_SOURCE_DIR}/src/BootstrapShaders.metal"
        -target "${OVERTE_IOS_METAL_TARGET}"
        -isysroot "${CMAKE_OSX_SYSROOT}"
        -o "${OVERTE_IOS_METAL_AIR}"
    COMMAND "${OVERTE_IOS_XCRUN}" --sdk "${OVERTE_IOS_SDK_NAME}" metallib
        "${OVERTE_IOS_METAL_AIR}"
        -o "${OVERTE_IOS_METALLIB}"
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
        "${OVERTE_IOS_METALLIB}"
        "${OVERTE_IOS_APP_BUNDLE}/default.metallib"
    COMMENT "Compiling and embedding iOS Metal shader library"
    VERBATIM
)

target_compile_definitions(OverteIOSBootstrap PRIVATE
    OVERTE_IOS_BOOTSTRAP=1
)

target_link_libraries(OverteIOSBootstrap PRIVATE
    "-framework AVFoundation"
    "-framework CoreGraphics"
    "-framework CoreMotion"
    "-framework Foundation"
    "-framework Metal"
    "-framework MetalKit"
    "-framework Network"
    "-framework UIKit"
)

set_target_properties(OverteIOSBootstrap PROPERTIES
    AUTOMOC OFF
    AUTORCC OFF
    AUTOUIC OFF
    MACOSX_BUNDLE_INFO_PLIST "${CMAKE_CURRENT_SOURCE_DIR}/resources/Info.plist.in"
    MACOSX_BUNDLE_BUNDLE_NAME "Overte"
    MACOSX_BUNDLE_BUNDLE_VERSION "1"
    MACOSX_BUNDLE_SHORT_VERSION_STRING "${PROJECT_VERSION}"
    XCODE_ATTRIBUTE_ASSETCATALOG_COMPILER_APPICON_NAME "AppIcon"
    XCODE_ATTRIBUTE_CODE_SIGN_STYLE "Automatic"
    XCODE_ATTRIBUTE_CLANG_ENABLE_OBJC_ARC "YES"
    XCODE_ATTRIBUTE_CURRENT_PROJECT_VERSION "1"
    XCODE_ATTRIBUTE_DEVELOPMENT_TEAM "${OVERTE_IOS_DEVELOPMENT_TEAM}"
    XCODE_ATTRIBUTE_ENABLE_BITCODE "NO"
    XCODE_ATTRIBUTE_GENERATE_INFOPLIST_FILE "NO"
    XCODE_ATTRIBUTE_IPHONEOS_DEPLOYMENT_TARGET "${CMAKE_OSX_DEPLOYMENT_TARGET}"
    XCODE_ATTRIBUTE_MARKETING_VERSION "${PROJECT_VERSION}"
    XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "${OVERTE_IOS_BUNDLE_IDENTIFIER}"
    XCODE_ATTRIBUTE_SUPPORTED_PLATFORMS "iphoneos iphonesimulator"
    XCODE_ATTRIBUTE_SUPPORTS_MACCATALYST "NO"
    XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1,2"
)

if(OVERTE_IOS_ENABLE_SIGNING)
    if(OVERTE_IOS_DEVELOPMENT_TEAM STREQUAL "")
        message(FATAL_ERROR
            "OVERTE_IOS_ENABLE_SIGNING requires OVERTE_IOS_DEVELOPMENT_TEAM")
    endif()
    set_target_properties(OverteIOSBootstrap PROPERTIES
        XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "YES"
        XCODE_ATTRIBUTE_CODE_SIGNING_REQUIRED "YES"
        XCODE_ATTRIBUTE_CODE_SIGN_ENTITLEMENTS "${CMAKE_CURRENT_SOURCE_DIR}/resources/Overte.entitlements"
    )
else()
    set_target_properties(OverteIOSBootstrap PROPERTIES
        XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO"
        XCODE_ATTRIBUTE_CODE_SIGNING_REQUIRED "NO"
    )
endif()
