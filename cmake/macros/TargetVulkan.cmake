# 
#  Created by Bradley Austin Davis on 2016/02/16
#
#  Distributed under the Apache License, Version 2.0.
#  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
# 
macro(TARGET_VULKAN)
    find_package(VulkanMemoryAllocator QUIET REQUIRED)
    target_link_libraries(${TARGET_NAME} GPUOpen::VulkanMemoryAllocator)

    if(IOS)
        find_package(MoltenVK QUIET REQUIRED)
        target_compile_definitions(${TARGET_NAME} PRIVATE VK_USE_PLATFORM_METAL_EXT)
        target_link_libraries(${TARGET_NAME}
            MoltenVK::MoltenVK
            "-framework Foundation"
            "-framework IOSurface"
            "-framework Metal"
            "-framework QuartzCore")
    else()
        find_package(Vulkan QUIET REQUIRED)
        target_include_directories(${TARGET_NAME} PRIVATE ${VULKAN_INCLUDE_DIR})
        target_link_libraries(${TARGET_NAME} ${VULKAN_LIBRARY})
        if(UNIX AND NOT APPLE AND NOT ANDROID)
            overte_find_qt(COMPONENTS X11Extras QUIET REQUIRED)
            target_link_libraries(${TARGET_NAME} "${OVERTE_QT_TARGET_PREFIX}X11Extras")
        endif()
    endif()
endmacro()
