# Copyright 2015, High Fidelity, Inc.
# Copyright 2022-2023 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

# Declare dependencies
macro (SETUP_TESTCASE_DEPENDENCIES)
  # link in the shared libraries
  link_hifi_libraries(shared audio audio-client plugins networking script-engine)

  package_libraries_for_deployment()

  if("${TARGET_NAME}" STREQUAL "audio-CodecTests")
    add_dependencies(${TARGET_NAME} pcmCodec opusCodec)
    if(APPLE AND NOT IOS)
      set(TEST_CODEC_PLUGIN_DIR "$<TARGET_FILE_DIR:${TARGET_NAME}>/../PlugIns")
    else()
      set(TEST_CODEC_PLUGIN_DIR "$<TARGET_FILE_DIR:${TARGET_NAME}>/plugins")
    endif()
    add_custom_command(TARGET ${TARGET_NAME} POST_BUILD
      COMMAND ${CMAKE_COMMAND} -E make_directory "${TEST_CODEC_PLUGIN_DIR}"
      COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "$<TARGET_FILE:pcmCodec>" "$<TARGET_FILE:opusCodec>"
        "${TEST_CODEC_PLUGIN_DIR}"
    )
  endif()
endmacro ()

setup_hifi_testcase()
