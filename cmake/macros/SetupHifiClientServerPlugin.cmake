#
#  Created by Brad Hefta-Gaub on 2016/07/07
#  Copyright 2016 High Fidelity, Inc.
#  Copyright 2025 Overte e.V.
#
#  Distributed under the Apache License, Version 2.0.
#  See the accompanying file LICENSE or http:#www.apache.org/licenses/LICENSE-2.0.html
#
macro(SETUP_HIFI_CLIENT_SERVER_PLUGIN)
  if (IOS)
    set(${TARGET_NAME}_SHARED 0)
  else()
    set(${TARGET_NAME}_SHARED 1)
  endif()
  set(PLUGIN_SUBFOLDER ${ARGN})
  setup_hifi_library()

  if (OVERTE_BUILD_CLIENT)
    if (IOS)
      if (NOT TARGET Overte)
        message(FATAL_ERROR "iOS static plug-in '${TARGET_NAME}' requires the Overte application target")
      endif()
      if (NOT DEFINED OVERTE_IOS_STATIC_PLUGIN_CLASS OR OVERTE_IOS_STATIC_PLUGIN_CLASS STREQUAL "")
        message(FATAL_ERROR "iOS static plug-in '${TARGET_NAME}' must declare OVERTE_IOS_STATIC_PLUGIN_CLASS")
      endif()
      target_compile_definitions(${TARGET_NAME} PRIVATE QT_STATICPLUGIN)
      target_link_libraries(Overte PRIVATE "$<LINK_LIBRARY:WHOLE_ARCHIVE,${TARGET_NAME}>")
      set_property(TARGET ${TARGET_NAME} PROPERTY OVERTE_IOS_STATIC_PLUGIN_CLASS "${OVERTE_IOS_STATIC_PLUGIN_CLASS}")
      set_property(TARGET ${TARGET_NAME} PROPERTY OVERTE_IOS_STATIC_PLUGIN_AUDITED TRUE)
    elseif (APPLE)
      add_dependencies(Overte ${TARGET_NAME})
    else()
      add_dependencies(interface ${TARGET_NAME})
    endif()
  endif()

  if (OVERTE_BUILD_SERVER)
    add_dependencies(assignment-client ${TARGET_NAME})
  endif()

  set_target_properties(${TARGET_NAME} PROPERTIES FOLDER "Plugins")

  if (APPLE AND NOT IOS)
    set(CLIENT_PLUGIN_PATH "${INTERFACE_BUNDLE_NAME}.app/Contents/PlugIns")
    set(SERVER_PLUGIN_PATH "plugins")
  else()
    set(CLIENT_PLUGIN_PATH "plugins")
    set(SERVER_PLUGIN_PATH "plugins")
  endif()

  if (PLUGIN_SUBFOLDER)
      set(CLIENT_PLUGIN_PATH "${CLIENT_PLUGIN_PATH}/${PLUGIN_SUBFOLDER}")
      set(SERVER_PLUGIN_PATH "${SERVER_PLUGIN_PATH}/${PLUGIN_SUBFOLDER}")
  endif()

  if (IOS)
    # Static iOS plug-ins are linked into Overte; no bundle copy path exists.
  elseif (CMAKE_SYSTEM_NAME MATCHES "Linux" OR CMAKE_GENERATOR STREQUAL "Unix Makefiles")
    set(CLIENT_PLUGIN_FULL_PATH "${CMAKE_BINARY_DIR}/interface/${CLIENT_PLUGIN_PATH}/")
    set(SERVER_PLUGIN_FULL_PATH "${CMAKE_BINARY_DIR}/assignment-client/${SERVER_PLUGIN_PATH}/")
  elseif (APPLE)
    set(CLIENT_PLUGIN_FULL_PATH "${CMAKE_BINARY_DIR}/interface/$<CONFIGURATION>/${CLIENT_PLUGIN_PATH}/")
    set(SERVER_PLUGIN_FULL_PATH "${CMAKE_BINARY_DIR}/assignment-client/$<CONFIGURATION>/${SERVER_PLUGIN_PATH}/")
  else()
    set(CLIENT_PLUGIN_FULL_PATH "${CMAKE_BINARY_DIR}/interface/$<CONFIGURATION>/${CLIENT_PLUGIN_PATH}/")
    set(SERVER_PLUGIN_FULL_PATH "${CMAKE_BINARY_DIR}/assignment-client/$<CONFIGURATION>/${SERVER_PLUGIN_PATH}/")
  endif()

  if (NOT IOS)
  # create the destination for the client plugin binaries
  add_custom_command(
    TARGET ${TARGET_NAME} POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E make_directory
    ${CLIENT_PLUGIN_FULL_PATH}
  )
  # copy the client plugin binaries
  add_custom_command(TARGET ${TARGET_NAME} POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E copy
    "$<TARGET_FILE:${TARGET_NAME}>"
    ${CLIENT_PLUGIN_FULL_PATH}
  )

  # create the destination for the server plugin binaries
  add_custom_command(
    TARGET ${TARGET_NAME} POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E make_directory
    ${SERVER_PLUGIN_FULL_PATH}
  )
  # copy the server plugin binaries
  add_custom_command(TARGET ${TARGET_NAME} POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E copy
    "$<TARGET_FILE:${TARGET_NAME}>"
    ${SERVER_PLUGIN_FULL_PATH}
  )
  endif()

endmacro()
