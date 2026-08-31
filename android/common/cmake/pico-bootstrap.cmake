file(MAKE_DIRECTORY "${CMAKE_BINARY_DIR}/cmake")
if(HIFI_ANDROID_HOST_TOOLS)
    if(NOT IS_DIRECTORY "${HIFI_ANDROID_HOST_TOOLS}")
        message(FATAL_ERROR "HIFI_ANDROID_HOST_TOOLS must name the prepared host-tool directory")
    endif()
    set(_android_host_tools_dir "${HIFI_ANDROID_HOST_TOOLS}")
else()
    set(_android_host_tools_dir "${CMAKE_CURRENT_LIST_DIR}/../../vr/pico/pico-host-tools")
endif()
set(ENV{SCRIBE_DIR} "${_android_host_tools_dir}")
set(ENV{GLSLANG_DIR} "${_android_host_tools_dir}")
set(ENV{SPIRV_CROSS_DIR} "${_android_host_tools_dir}")
set(ENV{SPIRV_TOOLS_DIR} "${_android_host_tools_dir}")

# Gradle invokes Ninja directly, so CMAKE_BUILD_PARALLEL_LEVEL alone does not
# limit native compilation. A CMake job pool carries the Pico host limit into
# Ninja without changing target-specific build logic.
if(DEFINED ENV{PICO_BUILD_JOBS} AND "$ENV{PICO_BUILD_JOBS}" MATCHES "^[1-9][0-9]*$")
    set_property(GLOBAL PROPERTY JOB_POOLS "android_compile=$ENV{PICO_BUILD_JOBS}" android_link=1)
    set(CMAKE_JOB_POOL_COMPILE android_compile)
    set(CMAKE_JOB_POOL_LINK android_link)
endif()

# AutoScribeShader includes this generated Conan file after consulting the
# environment.  The target dependency graph's copy points at Android ARM64
# executables, which cannot run while generating shaders on the Linux host.
file(WRITE "${CMAKE_BINARY_DIR}/cmake/ConanToolsDirs.cmake" [=[
set(GLSLANG_DIR "$ENV{GLSLANG_DIR}")
set(SCRIBE_DIR "$ENV{SCRIBE_DIR}")
set(SPIRV_CROSS_DIR "$ENV{SPIRV_CROSS_DIR}")
set(SPIRV_TOOLS_DIR "$ENV{SPIRV_TOOLS_DIR}")
]=])
unset(_android_host_tools_dir)

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
            "${CMAKE_CURRENT_LIST_DIR}/pico-compat"
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
                "${CMAKE_CURRENT_LIST_DIR}/pico-compat"
            )
        endif()
    endforeach()

    # Several legacy Android target macros skip find_package() but still link
    # the corresponding imported target. Load all resolved Conan targets once.
    if(HIFI_ANDROID_CONAN_GENERATORS)
        set(_android_conan_generators "${HIFI_ANDROID_CONAN_GENERATORS}")
    else()
        set(_android_conan_generators
            "${CMAKE_CURRENT_LIST_DIR}/../conan/pico4-debug/generators")
    endif()
    include("${_android_conan_generators}/conandeps_legacy.cmake")
    unset(_android_conan_generators)

    if(TARGET Qt5::AndroidExtras)
        file(GLOB _qt_jni_private_headers
            "${qt_PACKAGE_FOLDER_DEBUG}/include/QtCore/*/QtCore/private/qjni_p.h")
        list(LENGTH _qt_jni_private_headers _qt_jni_private_header_count)
        if(NOT _qt_jni_private_header_count EQUAL 1)
            message(FATAL_ERROR "Expected exactly one Qt Core private JNI header")
        endif()
        list(GET _qt_jni_private_headers 0 _qt_jni_private_header)
        get_filename_component(_qt_jni_private_dir "${_qt_jni_private_header}" DIRECTORY)
        get_filename_component(_qt_jni_qtcore_dir "${_qt_jni_private_dir}" DIRECTORY)
        get_filename_component(_qt_jni_version_dir "${_qt_jni_qtcore_dir}" DIRECTORY)
        set_property(
            TARGET Qt5::AndroidExtras APPEND PROPERTY INTERFACE_INCLUDE_DIRECTORIES
            "${_qt_jni_qtcore_dir}"
            "${_qt_jni_version_dir}"
        )
        unset(_qt_jni_private_headers)
        unset(_qt_jni_private_header_count)
        unset(_qt_jni_private_header)
        unset(_qt_jni_private_dir)
        unset(_qt_jni_qtcore_dir)
        unset(_qt_jni_version_dir)
    endif()
endif()
