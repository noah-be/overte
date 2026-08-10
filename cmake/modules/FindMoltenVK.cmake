# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

# Locate the static MoltenVK XCFramework distributed by Khronos. The caller may
# pass OVERTE_IOS_MOLTENVK_ROOT or set the environment variable of the same
# name. No system-wide fallback is used, keeping iOS builds reproducible.

set(OVERTE_IOS_MOLTENVK_ROOT "$ENV{OVERTE_IOS_MOLTENVK_ROOT}" CACHE PATH
    "Root of an unpacked MoltenVK distribution")

if(CMAKE_OSX_SYSROOT MATCHES "iphonesimulator")
    set(_moltenvk_slice "ios-arm64_x86_64-simulator")
else()
    set(_moltenvk_slice "ios-arm64")
endif()

set(_moltenvk_xcframework
    "${OVERTE_IOS_MOLTENVK_ROOT}/MoltenVK/static/MoltenVK.xcframework")
if(NOT EXISTS "${_moltenvk_xcframework}")
    # Retain compatibility with distributions predating the static/dynamic
    # package split.
    set(_moltenvk_xcframework
        "${OVERTE_IOS_MOLTENVK_ROOT}/MoltenVK/MoltenVK.xcframework")
endif()
set(_moltenvk_library
    "${_moltenvk_xcframework}/${_moltenvk_slice}/libMoltenVK.a")
if(EXISTS "${_moltenvk_library}")
    set(MoltenVK_LIBRARY "${_moltenvk_library}")
else()
    set(MoltenVK_LIBRARY "MoltenVK_LIBRARY-NOTFOUND")
endif()

find_path(MoltenVK_INCLUDE_DIR
    NAMES vulkan/vulkan.h
    HINTS
        "${OVERTE_IOS_MOLTENVK_ROOT}/MoltenVK/include"
        "${OVERTE_IOS_MOLTENVK_ROOT}/include"
    NO_DEFAULT_PATH
)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(MoltenVK
    REQUIRED_VARS MoltenVK_INCLUDE_DIR MoltenVK_LIBRARY)

if(MoltenVK_FOUND AND NOT TARGET MoltenVK::MoltenVK)
    add_library(MoltenVK::MoltenVK STATIC IMPORTED GLOBAL)
    set_target_properties(MoltenVK::MoltenVK PROPERTIES
        IMPORTED_LOCATION "${MoltenVK_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${MoltenVK_INCLUDE_DIR}"
    )
endif()

mark_as_advanced(MoltenVK_INCLUDE_DIR MoltenVK_LIBRARY)
