set(TARGET_NAME phoneInterface)
setup_hifi_library()
target_sources(${TARGET_NAME} PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/../../shared/src/QtInputConnectionCompat.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/PhoneUrlHandler.cpp"
)
link_hifi_libraries(
    shared task networking qml
    image model-serializers hfm render-utils physics entities octree
    gl gpu ${PLATFORM_GL_BACKEND}
)
target_include_directories(model-serializers SYSTEM PRIVATE
    "${HIFI_ANDROID_PRECOMPILED}/draco/include"
)

# Android does not ship pthread as a separately linkable library. Some of the
# legacy desktop-oriented target metadata still exposes it transitively.
get_target_property(PHONE_GPU_GL_LINK_LIBRARIES gpu-gl LINK_LIBRARIES)
list(REMOVE_ITEM PHONE_GPU_GL_LINK_LIBRARIES pthread)
set_property(TARGET gpu-gl PROPERTY LINK_LIBRARIES
    "${PHONE_GPU_GL_LINK_LIBRARIES}"
)
get_target_property(PHONE_GPU_GL_INTERFACE_LIBRARIES
    gpu-gl INTERFACE_LINK_LIBRARIES
)
list(REMOVE_ITEM PHONE_GPU_GL_INTERFACE_LIBRARIES pthread)
set_property(TARGET gpu-gl PROPERTY INTERFACE_LINK_LIBRARIES
    "${PHONE_GPU_GL_INTERFACE_LIBRARIES}"
)

target_opengl()
target_bullet()

# Initialize GL entry points even when an offscreen Qt context becomes current
# before the main 2D surface. This is an Android fix, not an OpenXR dependency.
get_target_property(PHONE_GL_SOURCES gl SOURCES)
list(FILTER PHONE_GL_SOURCES EXCLUDE REGEX "OffscreenGLCanvas\\.cpp$")
set_property(TARGET gl PROPERTY SOURCES "${PHONE_GL_SOURCES}")
target_sources(gl PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/../../shared/src/OffscreenGLCanvas.cpp"
)
target_include_directories(gl PRIVATE
    "${CMAKE_SOURCE_DIR}/libraries/gl/src/gl"
)
if (ANDROID_ABI STREQUAL "x86_64")
    # The Android Emulator exposes GLES 3.1 while the shared Android graphics
    # backend requests 3.2. The generated mobile shaders target GLSL ES 3.10,
    # so use the supported context version for the emulator-only ABI.
    target_compile_definitions(gl PRIVATE OVERTE_ANDROID_GLES31=1)
endif()

add_subdirectory("${CMAKE_SOURCE_DIR}/interface" "libraries/interface")
target_compile_options(audio-client PRIVATE -include jni.h)
include_directories("${CMAKE_SOURCE_DIR}/interface/src")
target_link_libraries(${TARGET_NAME} android log m interface)
