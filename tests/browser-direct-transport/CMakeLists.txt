# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
if (NOT OVERTE_BROWSER_TRANSPORT)
    return()
endif ()
find_package(LibDataChannel 0.24.6 EXACT CONFIG REQUIRED)

macro(setup_testcase_dependencies)
    link_hifi_libraries(shared networking script-engine avatars audio)
    target_link_libraries(${TARGET_NAME} LibDataChannel::LibDataChannel)
    package_libraries_for_deployment()
endmacro()

setup_hifi_testcase(Network WebSockets)
if (TARGET browser-direct-transport-WebRTCTransportTests)
    set_tests_properties(browser-direct-transport-WebRTCTransportTests-test PROPERTIES TIMEOUT 45)
endif ()
if (TARGET browser-direct-transport-NativeAvatarAudioWireTests)
    set_tests_properties(browser-direct-transport-NativeAvatarAudioWireTests-test PROPERTIES TIMEOUT 45)
endif ()
