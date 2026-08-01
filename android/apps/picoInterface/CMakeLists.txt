set(TARGET_NAME picoOpenXR)
setup_hifi_library()
target_openxr()
target_link_libraries(${TARGET_NAME} android log)

set(TARGET_NAME picoInterface)
setup_hifi_library()
target_sources(${TARGET_NAME} PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/src/QtInputConnectionCompat.cpp"
)
link_hifi_libraries(
    shared task networking qml
    image model-serializers hfm render-utils physics entities octree
    gl gpu ${PLATFORM_GL_BACKEND}
    picoOpenXR
)
target_include_directories(model-serializers SYSTEM PRIVATE
    "${HIFI_ANDROID_PRECOMPILED}/draco/include"
)
get_target_property(PICO_GPU_GL_LINK_LIBRARIES gpu-gl LINK_LIBRARIES)
list(REMOVE_ITEM PICO_GPU_GL_LINK_LIBRARIES pthread)
set_property(TARGET gpu-gl PROPERTY LINK_LIBRARIES
    "${PICO_GPU_GL_LINK_LIBRARIES}"
)
get_target_property(PICO_GPU_GL_INTERFACE_LIBRARIES
    gpu-gl INTERFACE_LINK_LIBRARIES
)
list(REMOVE_ITEM PICO_GPU_GL_INTERFACE_LIBRARIES pthread)
set_property(TARGET gpu-gl PROPERTY INTERFACE_LINK_LIBRARIES
    "${PICO_GPU_GL_INTERFACE_LIBRARIES}"
)
target_opengl()
target_bullet()

get_target_property(PICO_GL_SOURCES gl SOURCES)
list(FILTER PICO_GL_SOURCES EXCLUDE REGEX "OffscreenGLCanvas\\.cpp$")
set_property(TARGET gl PROPERTY SOURCES "${PICO_GL_SOURCES}")
target_sources(gl PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/overrides/OffscreenGLCanvas.cpp"
)
target_include_directories(gl PRIVATE
    "${CMAKE_SOURCE_DIR}/libraries/gl/src/gl"
)

add_subdirectory("${CMAKE_SOURCE_DIR}/interface" "libraries/interface")
get_target_property(PICO_INTERFACE_SOURCES interface SOURCES)
list(FILTER PICO_INTERFACE_SOURCES EXCLUDE REGEX "Application_Setup\\.cpp$")
set_property(TARGET interface PROPERTY SOURCES "${PICO_INTERFACE_SOURCES}")
target_sources(interface PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/overrides/Application_Setup.cpp"
)
target_compile_options(audio-client PRIVATE -include jni.h)
include_directories("${CMAKE_SOURCE_DIR}/interface/src")
target_link_libraries(${TARGET_NAME} android log m interface)
target_openxr()

# The upstream plugin list excludes all client plugins on Android. Pico uses
# the standard Overte OpenXR display/input plugin, so build and package it as
# an explicit dependency of this Android target.
set(DIR "openxr")
add_subdirectory(
    "${CMAKE_CURRENT_SOURCE_DIR}/openxr"
    "${CMAKE_BINARY_DIR}/plugins/openxr"
)
target_link_libraries(openxr picoOpenXR)
add_dependencies(${TARGET_NAME} openxr)
