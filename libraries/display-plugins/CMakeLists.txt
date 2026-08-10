set(TARGET_NAME display-plugins)
setup_hifi_library(Gui)

if(IOS AND OVERTE_RENDERING_BACKEND STREQUAL "Vulkan")
    set(OVERTE_IOS_EXCLUDED_OPENGL_DISPLAY_SOURCES
        src/display-plugins/Basic2DWindowOpenGLDisplayPlugin.cpp
        src/display-plugins/Basic2DWindowOpenGLDisplayPlugin.h
        src/display-plugins/OpenGLDisplayPlugin.cpp
        src/display-plugins/OpenGLDisplayPlugin.h
        src/display-plugins/hmd/DebugHmdDisplayPlugin.cpp
        src/display-plugins/hmd/DebugHmdDisplayPlugin.h
        src/display-plugins/hmd/HmdDisplayPlugin.cpp
        src/display-plugins/hmd/HmdDisplayPlugin.h
        src/display-plugins/stereo/InterleavedStereoDisplayPlugin.cpp
        src/display-plugins/stereo/InterleavedStereoDisplayPlugin.h
        src/display-plugins/stereo/SideBySideStereoDisplayPlugin.cpp
        src/display-plugins/stereo/SideBySideStereoDisplayPlugin.h
        src/display-plugins/stereo/StereoDisplayPlugin.cpp
        src/display-plugins/stereo/StereoDisplayPlugin.h
    )
    set_source_files_properties(${OVERTE_IOS_EXCLUDED_OPENGL_DISPLAY_SOURCES}
        PROPERTIES HEADER_FILE_ONLY TRUE SKIP_AUTOMOC TRUE)
endif()

set(DISPLAY_PLUGINS_GL_LIBRARY gl)
if(IOS AND OVERTE_RENDERING_BACKEND STREQUAL "Vulkan")
    # Every GL-typed display source or branch is excluded above or by the
    # OVERTE_IOS_VULKAN_DISABLE_QUICK_GL_COPY compile gate.
    set(DISPLAY_PLUGINS_GL_LIBRARY "")
endif()
link_hifi_libraries(shared shaders plugins ui-plugins ${DISPLAY_PLUGINS_GL_LIBRARY} ui render-utils ${PLATFORM_GL_BACKEND})
include_hifi_library_headers(gpu)
include_hifi_library_headers(material-networking)
include_hifi_library_headers(model-networking)
include_hifi_library_headers(networking)
include_hifi_library_headers(graphics)
include_hifi_library_headers(hfm)
include_hifi_library_headers(model-serializers)
include_hifi_library_headers(image)
include_hifi_library_headers(ktx)
include_hifi_library_headers(render)
include_hifi_library_headers(procedural)

# The native iOS Vulkan path gets its graphics API from gpu-vk/MoltenVK. Do not
# add a second, desktop OpenGL package requirement directly to display-plugins.
# Other platforms retain the established setup, including Android's EGL/glad.
if(IOS AND OVERTE_RENDERING_BACKEND STREQUAL "Vulkan")
    message(STATUS "display-plugins: skipping direct OpenGL setup for iOS Vulkan")
    target_compile_definitions(${TARGET_NAME} PRIVATE
        OVERTE_IOS_VULKAN_DISABLE_QUICK_GL_COPY=1)
else()
    set(OpenGL_GL_PREFERENCE "GLVND")
    target_opengl()
endif()

if (ANDROID AND HIFI_ANDROID_APP STREQUAL "phoneInterface")
    target_link_libraries(${TARGET_NAME} log)
endif()

GroupSources("src/display-plugins")
