# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

macro(setup_testcase_dependencies)
  link_hifi_libraries(shared hfm gpu graphics model-serializers model-baker networking animation image material-networking task procedural shaders ktx)
  if(TARGET_NAME STREQUAL "skinning-ShaderSkinningTests")
    link_hifi_libraries(render-utils render graphics-scripting model-networking material-networking task procedural ktx image entities-renderer)
    include_hifi_library_headers(audio)
    include_hifi_library_headers(octree)
    include_hifi_library_headers(script-engine)
    include_hifi_library_headers(entities)
    include_hifi_library_headers(physics)
    include_hifi_library_headers(avatars)
    include_hifi_library_headers(controllers)
    include_hifi_library_headers(pointers)
    include_hifi_library_headers(ui)
    include_hifi_library_headers(qml)
    include_hifi_library_headers(workload)
    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
      find_library(SKINNING_EGL_LIBRARY NAMES EGL REQUIRED)
      find_path(SKINNING_EGL_INCLUDE_DIR EGL/egl.h REQUIRED)
      target_include_directories(${TARGET_NAME} PRIVATE ${SKINNING_EGL_INCLUDE_DIR})
      target_link_libraries(${TARGET_NAME} ${SKINNING_EGL_LIBRARY})
      target_glad()
      if(OVERTE_USE_SYSTEM_LIBS)
        set(SCRIBE_DIR "$ENV{SCRIBE_DIR}")
        set(GLSLANG_DIR "$ENV{GLSLANG_DIR}")
      else()
        include(${CMAKE_BINARY_DIR}/cmake/ConanToolsDirs.cmake)
      endif()
      set(SKINNING_SHADER_DIR "${CMAKE_CURRENT_BINARY_DIR}/skinning-shaders")
      file(MAKE_DIRECTORY "${SKINNING_SHADER_DIR}")
      set(SKINNING_SHADER_OUTPUTS "")
      foreach(DQ RANGE 0 1)
        set(VERT "${SKINNING_SHADER_DIR}/skinning-${DQ}.vert")
        add_custom_command(OUTPUT "${VERT}" "${VERT}.spv"
          COMMAND "${SCRIBE_DIR}/scribe" -D GLPROFILE PC_GL -T vert -D TEST_DQ ${DQ}
            -H "${CMAKE_SOURCE_DIR}/libraries/shaders/headers/450/version.glsl"
            -H "${CMAKE_SOURCE_DIR}/libraries/shaders/headers/450/header.glsl"
            -I "${CMAKE_SOURCE_DIR}/libraries/render-utils/src/"
            -I "${CMAKE_SOURCE_DIR}/libraries/graphics/src/"
            "${CMAKE_CURRENT_SOURCE_DIR}/src/skinning.slv" -o "${VERT}"
          COMMAND "${GLSLANG_DIR}/glslangValidator" -G --auto-map-locations --auto-map-bindings
            -o "${VERT}.spv" "${VERT}"
          DEPENDS src/skinning.slv
            "${CMAKE_SOURCE_DIR}/libraries/render-utils/src/Skinning.slh"
            "${CMAKE_SOURCE_DIR}/libraries/graphics/src/graphics/ShaderConstants.h"
            "${CMAKE_SOURCE_DIR}/libraries/shaders/headers/450/version.glsl"
            "${CMAKE_SOURCE_DIR}/libraries/shaders/headers/450/header.glsl"
          VERBATIM)
        list(APPEND SKINNING_SHADER_OUTPUTS "${VERT}" "${VERT}.spv")
      endforeach()
      target_sources(${TARGET_NAME} PRIVATE ${SKINNING_SHADER_OUTPUTS})
      target_compile_definitions(${TARGET_NAME} PRIVATE TEST_SHADER_DIR="${SKINNING_SHADER_DIR}")
    endif()
  endif()
  package_libraries_for_deployment()
endmacro()

setup_hifi_testcase(Network)
