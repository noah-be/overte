#
#  Created by Bradley Austin Davis on 2018/10/29
#  Copyright 2018 High Fidelity, Inc.
#  Copyright 2024-2026 Overte e.V.
#
#  Distributed under the Apache License, Version 2.0.
#  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
#  SPDX-License-Identifier: Apache-2.0
#

set(TARGET_NAME vk)
setup_hifi_library(Gui)
if(IOS)
    enable_language(OBJCXX)
    target_sources(${TARGET_NAME} PRIVATE
        src/vk/VulkanIOSSurface.h
        src/vk/VulkanIOSSurface.mm
    )
endif()
GroupSources(src)
link_hifi_libraries(shared shaders gl)
overte_find_qt(COMPONENTS Core Gui QUIET REQUIRED)
# vk uses public Qt Core/Gui APIs only. A private GUI target would require
# version-matched private headers that Qt's iOS binary packages need not ship.

target_vulkan()
