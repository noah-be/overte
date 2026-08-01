file(MAKE_DIRECTORY "${CMAKE_BINARY_DIR}/cmake")
set(ENV{SCRIBE_DIR} "${CMAKE_CURRENT_LIST_DIR}/pico-host-tools")
set(ENV{GLSLANG_DIR} "${CMAKE_CURRENT_LIST_DIR}/pico-host-tools")
set(ENV{SPIRV_CROSS_DIR} "${CMAKE_CURRENT_LIST_DIR}/pico-host-tools")
set(ENV{SPIRV_TOOLS_DIR} "${CMAKE_CURRENT_LIST_DIR}/pico-host-tools")

# AutoScribeShader includes this generated Conan file after consulting the
# environment.  The target dependency graph's copy points at Android ARM64
# executables, which cannot run while generating shaders on the Linux host.
file(WRITE "${CMAKE_BINARY_DIR}/cmake/ConanToolsDirs.cmake" [=[
set(GLSLANG_DIR "$ENV{GLSLANG_DIR}")
set(SCRIBE_DIR "$ENV{SCRIBE_DIR}")
set(SPIRV_CROSS_DIR "$ENV{SPIRV_CROSS_DIR}")
set(SPIRV_TOOLS_DIR "$ENV{SPIRV_TOOLS_DIR}")
]=])

# The legacy Android CMake path expects desktop OpenGL and Qt modules which are
# either named differently or no longer shipped in our minimal Qt Android build.
if(ANDROID)
    add_compile_definitions(GL_APIENTRY=)

    if(NOT TARGET OpenGL::GL)
        add_library(OpenGL::GL INTERFACE IMPORTED)
        set_property(TARGET OpenGL::GL PROPERTY INTERFACE_LINK_LIBRARIES GLESv3)
    endif()

    if(NOT TARGET Qt5::AndroidExtras)
        add_library(Qt5::AndroidExtras INTERFACE IMPORTED)
        set_property(
            TARGET Qt5::AndroidExtras
            PROPERTY INTERFACE_INCLUDE_DIRECTORIES
            "${CMAKE_CURRENT_LIST_DIR}/cmake-pico-compat"
        )
    endif()

    if(NOT TARGET Qt5::WebView)
        add_library(Qt5::WebView INTERFACE IMPORTED)
    endif()

    foreach(_pico_qt_web_target WebEngineCore WebEngineWidgets)
        if(NOT TARGET Qt5::${_pico_qt_web_target})
            add_library(Qt5::${_pico_qt_web_target} INTERFACE IMPORTED)
            set_property(
                TARGET Qt5::${_pico_qt_web_target}
                PROPERTY INTERFACE_INCLUDE_DIRECTORIES
                "${CMAKE_CURRENT_LIST_DIR}/cmake-pico-compat"
            )
        endif()
    endforeach()

    # Several legacy Android target macros skip find_package() but still link
    # the corresponding imported target. Load all resolved Conan targets once.
    include(
        "${CMAKE_CURRENT_LIST_DIR}/conan/pico4-debug/generators/conandeps_legacy.cmake"
    )
endif()
