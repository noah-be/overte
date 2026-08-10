# Copyright 2013-2019, High Fidelity, Inc.
# Copyright 2022-2023 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set(TARGET_NAME audio-client)
if (ANDROID)
  set(PLATFORM_QT_COMPONENTS AndroidExtras)
endif ()
setup_hifi_library(Network Multimedia ${PLATFORM_QT_COMPONENTS})
if (IOS)
  enable_language(OBJCXX)
  target_sources(${TARGET_NAME} PRIVATE src/IOSAudioPermission.mm)
  find_library(AVFoundation AVFoundation REQUIRED)
  target_link_libraries(${TARGET_NAME} ${AVFoundation})
endif()
link_hifi_libraries(audio plugins)
include_hifi_library_headers(shared)
include_hifi_library_headers(networking)
include_hifi_library_headers(script-engine)

if (ANDROID)
else ()
  if (NOT DISABLE_WEBRTC )
    target_webrtc()
  else()
    message(WARNING "WebRTC is supported on this platform but has been disabled for this build (likely memory debugging)")
  endif()
endif ()

# append audio includes to our list of includes to bubble
target_include_directories(${TARGET_NAME} PUBLIC "${HIFI_LIBRARY_DIR}/audio/src")

if (WIN32)
  target_compile_definitions(${TARGET_NAME} PRIVATE WIN32)
endif()

# have CMake grab externals for us
if (APPLE AND NOT IOS)
  find_library(CoreAudio CoreAudio)
  find_library(CoreFoundation CoreFoundation)
  target_link_libraries(${TARGET_NAME} ${CoreAudio} ${CoreFoundation})
endif ()
