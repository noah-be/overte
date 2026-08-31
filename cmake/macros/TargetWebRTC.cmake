#
#  Copyright 2019 High Fidelity, Inc.
#  Copyright 2026 Overte e.V.
#
#  Distributed under the Apache License, Version 2.0.
#  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
#
macro(TARGET_WEBRTC)
    if (OVERTE_USE_SYSTEM_LIBS)
        find_package(PkgConfig REQUIRED)
        pkg_check_modules(WebRTC REQUIRED webrtc-audio-processing-2)
        target_include_directories(${TARGET_NAME} SYSTEM PUBLIC ${WebRTC_INCLUDE_DIRS})
        target_link_libraries(${TARGET_NAME} ${WebRTC_LINK_LIBRARIES})
    else()
        find_package(webrtc-audio-processing QUIET REQUIRED)
        target_link_libraries(${TARGET_NAME} webrtc-audio-processing::webrtc-audio-processing)
        if (IOS)
            # Conan Center's current Abseil component metadata contains the
            # correct static link graph but omits the package include root.
            # WebRTC's public API includes absl/*, so expose the exact resolved
            # package headers and fail during configure if the graph ever
            # stops providing that audited boundary.
            if (NOT DEFINED abseil_PACKAGE_FOLDER_RELEASE)
                message(FATAL_ERROR "The iOS WebRTC graph did not expose its Abseil package root")
            endif()
            set(_OVERTE_WEBRTC_ABSEIL_INCLUDE "${abseil_PACKAGE_FOLDER_RELEASE}/include")
            if (NOT EXISTS "${_OVERTE_WEBRTC_ABSEIL_INCLUDE}/absl/base/nullability.h")
                message(FATAL_ERROR "The iOS WebRTC graph lacks absl/base/nullability.h")
            endif()
            target_include_directories(${TARGET_NAME} SYSTEM PUBLIC "${_OVERTE_WEBRTC_ABSEIL_INCLUDE}")
            unset(_OVERTE_WEBRTC_ABSEIL_INCLUDE)
        endif()
    endif()
endmacro()
