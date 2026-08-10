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
target_link_libraries(Overte PRIVATE overte-ios-entity-integration)
target_link_libraries(Overte PRIVATE overte-ios-rendering-compatibility)
add_dependencies(Overte overte-ios-entity-integration)
