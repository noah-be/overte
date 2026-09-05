# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

if(NOT IOS)
    message(FATAL_ERROR
        "ios/integration may only be configured for an iOS toolchain")
endif()

include("${CMAKE_CURRENT_LIST_DIR}/EntityIntegrationGate.cmake")
overte_add_ios_entity_integration_gate(overte-ios-entity-integration)
include("${CMAKE_CURRENT_LIST_DIR}/RenderingCompatibilityPreflight.cmake")
overte_add_ios_rendering_compatibility_preflight(overte-ios-rendering-compatibility)

# Binding the gate to the real client makes it part of the generated link graph,
# not a documentation-only audit target. On Apple platforms Interface's bundle
# target is named Overte.
if(NOT TARGET Overte)
    message(FATAL_ERROR
        "iOS full-client entity integration requires the Overte application target")
endif()
target_link_libraries(Overte overte-ios-entity-integration)
target_link_libraries(Overte overte-ios-rendering-compatibility)
add_dependencies(Overte overte-ios-entity-integration)

# iOS-owned native storage/sink implementation. Shared registers its AccountManager
# consumer against the published PX-15 interface; the native primitive never
# falls back to AccountInfo.bin or defines account serialization itself.
target_sources(Overte PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/../src/SecureAccountStore.cpp"
    "${CMAKE_CURRENT_LIST_DIR}/../src/SecureAccountStore.mm"
    "${CMAKE_CURRENT_LIST_DIR}/../src/RedactingDiagnostics.mm"
    "${CMAKE_CURRENT_LIST_DIR}/../auth/KeychainAccountAdapter.cpp"
    "${CMAKE_CURRENT_LIST_DIR}/../auth/RegisterKeychainAccountStore.cpp"
    "${CMAKE_CURRENT_LIST_DIR}/../diagnostics/InstallSafeQtLogging.cpp"
)
set_source_files_properties(
    "${CMAKE_CURRENT_LIST_DIR}/../src/SecureAccountStore.mm"
    "${CMAKE_CURRENT_LIST_DIR}/../src/RedactingDiagnostics.mm"
    PROPERTIES COMPILE_OPTIONS "-fobjc-arc"
)
target_link_libraries(Overte "-framework Security" "-framework LocalAuthentication")

# Real Full Client caller: a foreground-only, 30-second native metrics sampler.
# Render-budget adaptation remains the Shared renderer's responsibility.
target_sources(Overte PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/../performance/NativeMetrics.cpp"
    "${CMAKE_CURRENT_LIST_DIR}/../performance/NativeMetrics.mm"
    "${CMAKE_CURRENT_LIST_DIR}/../performance/FullClientMetrics.mm"
)
