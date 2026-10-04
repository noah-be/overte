# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0

macro(TARGET_DATACHANNEL)
    # Separate from audio processing and the qualified Conan dependency graph.
    find_package(LibDataChannel 0.24.6 EXACT CONFIG REQUIRED)
    target_link_libraries(${TARGET_NAME} LibDataChannel::LibDataChannel)
    target_compile_definitions(${TARGET_NAME} PUBLIC OVERTE_BROWSER_TRANSPORT=1)
endmacro()
