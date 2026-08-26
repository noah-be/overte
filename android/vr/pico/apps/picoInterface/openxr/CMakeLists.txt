#
# Copyright 2024 Lubosz Sarnecki
# Copyright 2024 Overte e.V.
#
# SPDX-License-Identifier: Apache-2.0
#

set(TARGET_NAME openxr)
setup_hifi_plugin(Gui Qml Multimedia)
link_hifi_libraries(shared task gl qml networking controllers ui
    plugins display-plugins ui-plugins input-plugins
    audio-client render-utils graphics shaders gpu render
    material-networking model-networking model-baker hfm
    model-serializers ktx image procedural ${PLATFORM_GL_BACKEND})
include_hifi_library_headers(octree)
include_hifi_library_headers(script-engine)

target_openxr()

# The explicit input layer is available only to the Android Debug variant.
# Release/RelWithDebInfo builds do not compile, link, or package its binary,
# manifest, marker, or transport implementation.
if(ANDROID AND OVERTE_PICO_E2E_OPENXR_INPUT)
    add_library(overte_e2e_openxr_input SHARED
        e2e_input/E2eInputProtocol.cpp
        e2e_input/E2eInputProtocol.h
        e2e_input/XrApiLayer.cpp
    )
    set_target_properties(overte_e2e_openxr_input PROPERTIES
        OUTPUT_NAME "XrApiLayer_overte_e2e_input"
        CXX_VISIBILITY_PRESET hidden
        VISIBILITY_INLINES_HIDDEN YES
    )
    target_compile_features(overte_e2e_openxr_input PRIVATE cxx_std_17)
    target_include_directories(overte_e2e_openxr_input PRIVATE ${OpenXR_INCLUDE_DIRS})
    target_link_libraries(overte_e2e_openxr_input PRIVATE Qt5::Core android log)

    # A real symbol reference keeps the layer in the APK's native dependency
    # graph while xrCreateInstance still activates it explicitly by name.
    target_link_libraries(openxr overte_e2e_openxr_input)
    target_compile_definitions(openxr PRIVATE OVERTE_E2E_OPENXR_INPUT_V1=1)
endif()

target_include_directories(openxr PRIVATE
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../../common/openxr")

if(CMAKE_CXX_COMPILER_ID MATCHES "GNU")
    # Silence GCC warnings
    target_compile_options(openxr PRIVATE -Wno-missing-field-initializers)
endif()
