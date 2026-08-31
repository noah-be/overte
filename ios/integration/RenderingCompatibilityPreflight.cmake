# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

include_guard(GLOBAL)

set(OVERTE_IOS_RENDERING_COMPAT_REQUIRED_TARGETS qml vk gl display-plugins)

function(overte_add_ios_rendering_compatibility_preflight gate_target)
    if(TARGET "${gate_target}")
        message(FATAL_ERROR "iOS rendering compatibility preflight target '${gate_target}' already exists")
    endif()

    set(missing_targets "")
    foreach(required_target IN LISTS OVERTE_IOS_RENDERING_COMPAT_REQUIRED_TARGETS)
        if(NOT TARGET "${required_target}")
            list(APPEND missing_targets "${required_target}")
        endif()
    endforeach()
    if(missing_targets)
        list(JOIN missing_targets ", " missing_targets_text)
        message(FATAL_ERROR
            "iOS rendering compatibility preflight is fail-closed: missing target(s): ${missing_targets_text}")
    endif()

    if(DEFINED OVERTE_IOS_COMPAT_SOURCE_ROOT)
        set(source_root "${OVERTE_IOS_COMPAT_SOURCE_ROOT}")
    else()
        set(source_root "${CMAKE_SOURCE_DIR}")
    endif()
    set(required_headers
        "libraries/qml/src/qml/OffscreenSurface.h"
        "libraries/vk/src/vk/VKWidget.h"
        "libraries/gl/src/gl/OffscreenGLCanvas.h")
    foreach(relative_header IN LISTS required_headers)
        if(NOT EXISTS "${source_root}/${relative_header}")
            message(FATAL_ERROR
                "iOS rendering compatibility preflight is fail-closed: missing required public header: ${relative_header}")
        endif()
    endforeach()

    get_target_property(display_definitions display-plugins COMPILE_DEFINITIONS)
    if(NOT display_definitions)
        set(display_definitions "")
    endif()
    get_target_property(display_interface_definitions display-plugins INTERFACE_COMPILE_DEFINITIONS)
    if(display_interface_definitions)
        list(APPEND display_definitions ${display_interface_definitions})
    endif()
    list(FIND display_definitions "OVERTE_IOS_VULKAN_DISABLE_QUICK_GL_COPY=1" quick_copy_gate_index)
    if(quick_copy_gate_index EQUAL -1)
        message(FATAL_ERROR
            "iOS rendering compatibility preflight is fail-closed: display-plugins lacks "
            "OVERTE_IOS_VULKAN_DISABLE_QUICK_GL_COPY=1")
    endif()

    add_library("${gate_target}" INTERFACE)
    target_compile_definitions("${gate_target}" INTERFACE
        OVERTE_IOS_RENDERING_COMPATIBILITY_PREFLIGHT=1)
    set_property(TARGET "${gate_target}" PROPERTY
        OVERTE_IOS_RENDERING_COMPATIBILITY_AUDITED TRUE)
endfunction()
