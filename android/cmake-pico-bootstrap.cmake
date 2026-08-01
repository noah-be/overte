file(MAKE_DIRECTORY "${CMAKE_BINARY_DIR}/cmake")
file(
    COPY "${CMAKE_CURRENT_LIST_DIR}/conan/pico4-debug/cmake/ConanToolsDirs.cmake"
    DESTINATION "${CMAKE_BINARY_DIR}/cmake"
)

set(ENV{SCRIBE_DIR} "${CMAKE_CURRENT_LIST_DIR}/pico-host-tools")
set(ENV{GLSLANG_DIR} "${CMAKE_CURRENT_LIST_DIR}/pico-host-tools")
set(ENV{SPIRV_CROSS_DIR} "${CMAKE_CURRENT_LIST_DIR}/pico-host-tools")
set(ENV{SPIRV_TOOLS_DIR} "${CMAKE_CURRENT_LIST_DIR}/pico-host-tools")

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
