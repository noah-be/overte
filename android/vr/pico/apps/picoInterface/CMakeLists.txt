set(TARGET_NAME picoOpenXR)
setup_hifi_library()
include("${CMAKE_CURRENT_SOURCE_DIR}/../../cmake/pico-qt-host-tools.cmake")
pico_bind_qt_host_tools(picoOpenXR)
target_openxr()
target_link_libraries(${TARGET_NAME} android log)
target_sources(picoOpenXR PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/security/PicoAccountStore.cpp")
target_sources(picoOpenXR PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/audio/PicoAudioLifecycle.cpp")

set(TARGET_NAME picoInterface)
setup_hifi_library()
pico_bind_qt_host_tools(picoInterface)
get_target_property(PICO_INTERFACE_SOURCES picoInterface SOURCES)
list(FILTER PICO_INTERFACE_SOURCES EXCLUDE REGEX "PicoWebViewItem\\.(cpp|h)$")
set_property(TARGET picoInterface PROPERTY SOURCES "${PICO_INTERFACE_SOURCES}")
target_sources(picoInterface PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../common/src/QtInputConnectionCompat.cpp"
)
# setup_hifi_library() keeps the directory's native library target while this
# standalone Android CMake file switches TARGET_NAME.  The Pico-specific QML
# item therefore needs its Qt GUI dependencies explicitly on that target.
target_link_libraries(picoOpenXR Qt5::Gui Qt5::Qml Qt5::Quick)
link_hifi_libraries(
    shared task networking qml
    image model-serializers hfm render-utils physics entities octree
    gl gpu ${PLATFORM_GL_BACKEND}
    picoOpenXR
)
target_include_directories(model-serializers SYSTEM PRIVATE
    "${PICO_DRACO_INCLUDE}"
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
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../common/src/OffscreenGLCanvas.cpp"
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
    "${CMAKE_CURRENT_SOURCE_DIR}/lifecycle/PicoClientVisibility.cpp"
)
# Application setup consumes the single account-store instance in picoOpenXR.
# Link its owning library directly so libinterface resolves that symbol.
target_link_libraries(interface picoOpenXR)
if(OVERTE_PICO_E2E_OPENXR_INPUT)
    target_compile_definitions(interface PRIVATE OVERTE_E2E_OPENXR_INPUT_V1=1)
    target_sources(interface PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/e2e/PicoE2eTabletBridge.cpp"
        "${CMAKE_CURRENT_SOURCE_DIR}/e2e/PicoE2eTabletBridge.h"
    )
endif()
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
