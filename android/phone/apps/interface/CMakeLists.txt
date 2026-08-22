set(TARGET_NAME native-lib)
setup_hifi_library(Core5Compat)
link_hifi_libraries(shared task networking gl gpu qml image model-serializers hfm render-utils physics entities octree ${PLATFORM_GL_BACKEND})
target_opengl()
target_bullet()

set(INTERFACE_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../../../../interface")
add_subdirectory("${INTERFACE_DIR}" "libraries/interface")
include_directories("${INTERFACE_DIR}/src")

target_link_libraries(native-lib android log m interface)
target_include_directories(native-lib PRIVATE "libraries/ui/src")
target_link_libraries(native-lib ui)
