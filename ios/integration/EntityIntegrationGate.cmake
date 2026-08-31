# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

include_guard(GLOBAL)

set(OVERTE_IOS_ENTITY_REQUIRED_TARGETS
    networking
    octree
    entities
    entities-renderer
)

function(overte_add_ios_entity_integration_gate gate_target)
    if(TARGET "${gate_target}")
        message(FATAL_ERROR
            "iOS entity integration gate target '${gate_target}' already exists")
    endif()

    set(missing_targets "")
    foreach(required_target IN LISTS OVERTE_IOS_ENTITY_REQUIRED_TARGETS)
        if(NOT TARGET "${required_target}")
            list(APPEND missing_targets "${required_target}")
        endif()
    endforeach()

    if(missing_targets)
        list(JOIN missing_targets ", " missing_targets_text)
        message(FATAL_ERROR
            "iOS full-client entity integration is fail-closed: missing native "
            "Overte target(s): ${missing_targets_text}. Configure with "
            "OVERTE_BUILD_CLIENT=ON and add ios/integration only after the "
            "Interface graph has created networking, octree, entities, and "
            "entities-renderer. Do not substitute a bootstrap protocol copy.")
    endif()

    add_library("${gate_target}" INTERFACE)
    target_link_libraries("${gate_target}" INTERFACE
        networking
        octree
        entities
        entities-renderer
    )
    target_compile_definitions("${gate_target}" INTERFACE
        OVERTE_IOS_NATIVE_ENTITY_GRAPH=1
    )
    set_property(TARGET "${gate_target}" PROPERTY
        OVERTE_IOS_ENTITY_INTEGRATION_AUDITED TRUE)
endfunction()
