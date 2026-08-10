#
#  Created by Brad Davis on 2018/11/10
#  Copyright 2018 High Fidelity, Inc.
#  Copyright 2024-2025 Overte e.V.
#
#  Distributed under the Apache License, Version 2.0.
#  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
#

set(TARGET_NAME gpu-vk)
setup_hifi_library()
if(IOS)
    link_hifi_libraries(shared shaders vk gpu render-utils)
else()
    link_hifi_libraries(shared shaders vk gl gpu render-utils)
endif()
GroupSources("src")

if(IOS)
    # MoltenVK cannot import desktop OpenGL memory objects or GLsync fences.
    # Keep external textures fail-closed until a native IOSurface/Metal import
    # implementation replaces that desktop-only interoperability path.
    target_compile_definitions(${TARGET_NAME} PUBLIC
        OVERTE_IOS_VULKAN_DISABLE_EXTERNAL_GL_INTEROP=1)
endif()

target_vulkan()
