set(TARGET_NAME picoOpenXR)
setup_hifi_library()
# Conan's cross-compiled Qt package exposes host tools without a
# RelWithDebInfo-specific location. Android release variants use that
# configuration, so copy the checksum-pinned host-tool locations explicitly.
foreach(PICO_QT_TOOL moc rcc qmake uic)
    if(TARGET Qt5::${PICO_QT_TOOL})
        get_target_property(PICO_QT_TOOL_LOCATION Qt5::${PICO_QT_TOOL} IMPORTED_LOCATION)
        if(PICO_QT_TOOL_LOCATION)
            set_property(TARGET Qt5::${PICO_QT_TOOL} PROPERTY
                IMPORTED_LOCATION_RELWITHDEBINFO "${PICO_QT_TOOL_LOCATION}")
        endif()
    endif()
endforeach()
get_target_property(PICO_QT_MOC Qt5::moc IMPORTED_LOCATION)
if(PICO_QT_MOC)
    set_property(TARGET picoOpenXR PROPERTY AUTOMOC_EXECUTABLE "${PICO_QT_MOC}")
endif()
get_target_property(PICO_QT_RCC Qt5::rcc IMPORTED_LOCATION)
if(PICO_QT_RCC)
    set_property(TARGET picoOpenXR PROPERTY AUTORCC_EXECUTABLE "${PICO_QT_RCC}")
endif()
get_target_property(PICO_QT_UIC Qt5::uic IMPORTED_LOCATION)
if(PICO_QT_UIC)
    set_property(TARGET picoOpenXR PROPERTY AUTOUIC_EXECUTABLE "${PICO_QT_UIC}")
endif()
target_openxr()
target_link_libraries(${TARGET_NAME} android log)

set(TARGET_NAME picoInterface)
setup_hifi_library()
# Reapply after the second Qt discovery and bind the host tools to this target.
foreach(PICO_QT_TOOL moc rcc qmake uic)
    get_target_property(PICO_QT_TOOL_LOCATION Qt5::${PICO_QT_TOOL} IMPORTED_LOCATION)
    if(PICO_QT_TOOL_LOCATION)
        set_property(TARGET Qt5::${PICO_QT_TOOL} PROPERTY
            IMPORTED_LOCATION_RELWITHDEBINFO "${PICO_QT_TOOL_LOCATION}")
    endif()
endforeach()
set_target_properties(Qt5::moc PROPERTIES IMPORTED_LOCATION_RELWITHDEBINFO "${PICO_QT_MOC}")
set_target_properties(Qt5::rcc PROPERTIES IMPORTED_LOCATION_RELWITHDEBINFO "${PICO_QT_RCC}")
set_target_properties(Qt5::uic PROPERTIES IMPORTED_LOCATION_RELWITHDEBINFO "${PICO_QT_UIC}")
set_property(TARGET Qt5::moc PROPERTY MAP_IMPORTED_CONFIG_RELWITHDEBINFO "")
set_property(TARGET Qt5::rcc PROPERTY MAP_IMPORTED_CONFIG_RELWITHDEBINFO "")
set_property(TARGET Qt5::uic PROPERTY MAP_IMPORTED_CONFIG_RELWITHDEBINFO "")
set_property(TARGET picoInterface PROPERTY AUTOMOC_EXECUTABLE "${PICO_QT_MOC}")
set_property(TARGET picoInterface PROPERTY AUTORCC_EXECUTABLE "${PICO_QT_RCC}")
set_property(TARGET picoInterface PROPERTY AUTOUIC_EXECUTABLE "${PICO_QT_UIC}")
get_target_property(PICO_INTERFACE_SOURCES picoInterface SOURCES)
list(FILTER PICO_INTERFACE_SOURCES EXCLUDE REGEX "PicoWebViewItem\\.(cpp|h)$")
set_property(TARGET picoInterface PROPERTY SOURCES "${PICO_INTERFACE_SOURCES}")
target_sources(picoInterface PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/../../shared/src/QtInputConnectionCompat.cpp"
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
    "${CMAKE_CURRENT_SOURCE_DIR}/../../shared/src/OffscreenGLCanvas.cpp"
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
