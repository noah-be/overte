# Copyright 2013-2019 High Fidelity, Inc.
# Copyright 2019-2021 Vircadia contributors
# Copyright 2021-2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

if (APPLE)
  # Make the OSX DMG app be Overte.app.
  set(TARGET_NAME Overte)
else()
  set(TARGET_NAME interface)
endif()

project(${TARGET_NAME})

file(GLOB_RECURSE QML_SRC CONFIGURE_DEPENDS resources/qml/*.qml resources/qml/*.js)
add_custom_target(qmls SOURCES ${QML_SRC})
GroupSources("resources/qml")

function(JOIN VALUES GLUE OUTPUT)
  string (REGEX REPLACE "([^\\]|^);" "\\1${GLUE}" _TMP_STR "${VALUES}")
  string (REGEX REPLACE "[\\](.)" "\\1" _TMP_STR "${_TMP_STR}") #fixes escaping
  set (${OUTPUT} "${_TMP_STR}" PARENT_SCOPE)
endfunction()

set(CUSTOM_INTERFACE_QRC_PATHS "")

set(INTERFACE_QT_COMPONENTS
  Gui Widgets Multimedia Network Qml Quick Svg
  ${PLATFORM_QT_COMPONENTS}
  WebChannel WebSockets
)
if(NOT IOS)
  list(APPEND INTERFACE_QT_COMPONENTS WebEngineCore WebEngineWidgets)
endif()
overte_find_qt(COMPONENTS ${INTERFACE_QT_COMPONENTS} QUIET REQUIRED)


if (OVERTE_BUILD_TOOLS AND JSDOC_ENABLED)
    message(STATUS "JSDoc enabled, depending on jsdoc")
    add_custom_qrc_path(CUSTOM_INTERFACE_QRC_PATHS "${CMAKE_BINARY_DIR}/tools/jsdoc/out/hifiJSDoc.json" "auto-complete/hifiJSDoc.json")
endif()

set(RESOURCES_QRC ${CMAKE_CURRENT_BINARY_DIR}/resources.qrc)
set(RESOURCES_RCC ${CMAKE_CURRENT_BINARY_DIR}/resources.rcc)
set(INTERFACE_QRC_EXCLUDES "")
if (HIFI_ANDROID AND HIFI_ANDROID_APP STREQUAL "phoneInterface")
  # Android's NetworkTexture path never selects TextureMeta::uncompressed; it
  # uses a supported ETC2/BPTC entry or the original image fallback instead.
  # Avoid carrying two unused 32 MiB default-sky KTX files in the phone RCC.
  list(APPEND INTERFACE_QRC_EXCLUDES
    "^images/Default-Sky-9-cubemap/Default-Sky-9-cubemap(-ambient)?[.]ktx$"
    # Phone uses a Basic2D display and its minimal default script set does not
    # load the Vive/Oculus controller-model scripts. The touchscreen virtual
    # pad is packaged under scripts/system assets instead.
    "^meshes/controller/.*")
endif()
generate_qrc(
  OUTPUT ${RESOURCES_QRC}
  PATH ${CMAKE_CURRENT_SOURCE_DIR}/resources
  CUSTOM_PATHS ${CUSTOM_INTERFACE_QRC_PATHS}
  GLOBS *
  EXCLUDES ${INTERFACE_QRC_EXCLUDES})

if (ANDROID)
  # on Android, don't compress the rcc binary
  overte_qt_add_binary_resources(resources "${RESOURCES_QRC}" DESTINATION "${RESOURCES_RCC}" OPTIONS -no-compress)
else ()
  overte_qt_add_binary_resources(resources "${RESOURCES_QRC}" DESTINATION "${RESOURCES_RCC}")
endif()

if (OVERTE_BUILD_TOOLS AND JSDOC_ENABLED)
    add_dependencies(resources jsdoc)
endif()

list(APPEND GENERATE_QRC_DEPENDS ${RESOURCES_RCC})

# set a default root dir for each of our optional externals if it was not passed
set(OPTIONAL_EXTERNALS "LeapMotion")

setup_memory_debugger()
setup_thread_debugger()

foreach(EXTERNAL ${OPTIONAL_EXTERNALS})
  string(TOUPPER ${EXTERNAL} ${EXTERNAL}_UPPERCASE)
  if (NOT ${${EXTERNAL}_UPPERCASE}_ROOT_DIR)
    string(TOLOWER ${EXTERNAL} ${EXTERNAL}_LOWERCASE)
    set(${${EXTERNAL}_UPPERCASE}_ROOT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/external/${${EXTERNAL}_LOWERCASE}")
  endif ()
endforeach()

# find_package(Qt5LinguistTools QUIET REQUIRED)
# find_package(Qt5LinguistToolsMacros)

if (WIN32)
  set(CMAKE_CXX_FLAGS_DEBUG  "${CMAKE_CXX_FLAGS_DEBUG} -bigobj")
  add_definitions(-D_USE_MATH_DEFINES) # apparently needed to get M_PI and other defines from cmath/math.h
  add_definitions(-DWINDOWS_LEAN_AND_MEAN) # needed to make sure windows doesn't go to crazy with its defines
endif()

# grab the implementation and header files from src dirs
file(GLOB_RECURSE INTERFACE_SRCS "src/*.cpp" "src/*.h")

# The Vulkan application constructs VKCanvas and never references GLCanvas.
# Do not parse or moc the legacy OpenGL widget in the iOS Vulkan graph.
if(IOS AND OVERTE_RENDERING_BACKEND STREQUAL "Vulkan")
  list(REMOVE_ITEM INTERFACE_SRCS
    "${CMAKE_CURRENT_SOURCE_DIR}/src/GLCanvas.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/GLCanvas.h")
endif()

# iOS packages update through their signing/distribution channel. The runtime
# entry points are guarded in source, so do not moc/compile the desktop update
# dialog or retain its otherwise unused updater library at link time.
set(INTERFACE_AUTO_UPDATER_LIBRARY auto-updater)
if(IOS)
  list(REMOVE_ITEM INTERFACE_SRCS
    "${CMAKE_CURRENT_SOURCE_DIR}/src/ui/BaseLogDialog.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/ui/BaseLogDialog.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/ui/DomainConnectionDialog.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/ui/DomainConnectionDialog.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/ui/EntityScriptServerLogDialog.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/ui/EntityScriptServerLogDialog.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/ui/LogDialog.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/ui/LogDialog.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/ui/LodToolsDialog.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/ui/LodToolsDialog.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/ui/OctreeStatsDialog.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/ui/OctreeStatsDialog.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/ui/StandAloneJSConsole.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/ui/StandAloneJSConsole.h"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/ui/UpdateDialog.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/ui/UpdateDialog.h")
  set(INTERFACE_AUTO_UPDATER_LIBRARY "")
endif()

GroupSources("src")
list(APPEND INTERFACE_SRCS ${RESOURCES_RCC})

# grab the Objective-C sources on OS X
if (APPLE)
  file(GLOB_RECURSE INTERFACE_OBJCPP_SRCS "src/*.m" "src/*.mm")
  if (IOS)
    # App Nap is a macOS process policy and has no iOS implementation. Keep
    # the desktop Objective-C++ source out of the iphoneos compile graph.
    get_filename_component(APP_NAP_DISABLER_MM "src/AppNapDisabler.mm" ABSOLUTE)
    list(REMOVE_ITEM INTERFACE_OBJCPP_SRCS ${APP_NAP_DISABLER_MM})
    # NSSpeechRecognizer is an AppKit service. iOS has no implementation and
    # its consumers are excluded below at the source level.
    get_filename_component(SPEECH_RECOGNIZER_MM "src/SpeechRecognizer.mm" ABSOLUTE)
    list(REMOVE_ITEM INTERFACE_OBJCPP_SRCS ${SPEECH_RECOGNIZER_MM})
  endif()
  list(APPEND INTERFACE_SRCS ${INTERFACE_OBJCPP_SRCS})
endif ()

# Add SpeechRecognizer if on Windows or OS X, otherwise remove
if (WIN32)
  # Use .cpp and .h files as is.
elseif (APPLE AND NOT IOS)
  get_filename_component(SPEECHRECOGNIZER_CPP "src/SpeechRecognizer.cpp" ABSOLUTE)
  list(REMOVE_ITEM INTERFACE_SRCS ${SPEECHRECOGNIZER_CPP})
else ()
  get_filename_component(SPEECHRECOGNIZER_H "src/SpeechRecognizer.h" ABSOLUTE)
  list(REMOVE_ITEM INTERFACE_SRCS ${SPEECHRECOGNIZER_H})
  get_filename_component(SPEECHRECOGNIZER_CPP "src/SpeechRecognizer.cpp" ABSOLUTE)
  list(REMOVE_ITEM INTERFACE_SRCS ${SPEECHRECOGNIZER_CPP})
endif ()

# grab the ui files in resources/ui
file (GLOB_RECURSE QT_UI_FILES ui/*.ui)
source_group("UI Files" FILES ${QT_UI_FILES})
# have qt5 wrap them and generate the appropriate header files
overte_qt_wrap_ui(QT_UI_HEADERS "${QT_UI_FILES}")

# add them to the interface source files
set(INTERFACE_SRCS ${INTERFACE_SRCS} "${QT_UI_HEADERS}" "${QT_RESOURCES}")

# translation disabled until we strip out the line numbers
# set(QM ${TARGET_NAME}_en.qm)
# set(TS ${TARGET_NAME}_en.ts)
# qt5_create_translation_custom(${QM} ${INTERFACE_SRCS} ${QT_UI_FILES} ${TS})

# setup the android parameters that will help us produce an APK
if (ANDROID)
  set(ANDROID_SDK_ROOT $ENV{ANDROID_HOME})
  set(BUILD_SHARED_LIBS ON)
endif ()

if (APPLE)

  # configure CMake to use a custom Info.plist
  if (IOS)
    if (NOT DEFINED OVERTE_IOS_BUNDLE_IDENTIFIER OR OVERTE_IOS_BUNDLE_IDENTIFIER STREQUAL "")
      message(FATAL_ERROR "The integrated iOS client requires OVERTE_IOS_BUNDLE_IDENTIFIER")
    endif()
    if (OVERTE_IOS_ENABLE_SIGNING)
      if (NOT DEFINED OVERTE_IOS_DEVELOPMENT_TEAM OR OVERTE_IOS_DEVELOPMENT_TEAM STREQUAL "")
        message(FATAL_ERROR "Integrated iOS signing requires OVERTE_IOS_DEVELOPMENT_TEAM")
      endif()
    endif()
  endif()

  set(MACOSX_BUNDLE_BUNDLE_NAME "Overte")
  if (PRODUCTION_BUILD)
    set(MACOSX_BUNDLE_GUI_IDENTIFIER org.overte.interface)
  else ()
    if (DEV_BUILD)
      set(MACOSX_BUNDLE_GUI_IDENTIFIER org.overte.interface-dev)
    elseif (PR_BUILD)
      set(MACOSX_BUNDLE_GUI_IDENTIFIER org.overte.interface-pr)
    endif ()
  endif ()

  # set how the icon shows up in the Info.plist file
  set(MACOSX_BUNDLE_ICON_FILE "${INTERFACE_ICON_FILENAME}")

  # set where in the bundle to put the resources file
  set_source_files_properties(${CMAKE_CURRENT_SOURCE_DIR}/icon/${INTERFACE_ICON_FILENAME} PROPERTIES MACOSX_PACKAGE_LOCATION Resources)

  # append the discovered resources to our list of interface sources
  list(APPEND INTERFACE_SRCS ${CMAKE_CURRENT_SOURCE_DIR}/icon/${INTERFACE_ICON_FILENAME})
endif()

if (UNIX AND NOT IOS)
  set(BUILD_SHARED_LIBS ON)
endif ()

# create the executable, make it a bundle on OS X
if (APPLE)
  add_executable(${TARGET_NAME} MACOSX_BUNDLE ${INTERFACE_SRCS} ${QM})
  if (IOS)
    set_target_properties(${TARGET_NAME} PROPERTIES
      MACOSX_BUNDLE_INFO_PLIST "${CMAKE_SOURCE_DIR}/ios/resources/InterfaceInfo.plist.in"
      XCODE_ATTRIBUTE_GENERATE_INFOPLIST_FILE "NO"
      XCODE_ATTRIBUTE_CODE_SIGN_ENTITLEMENTS "${CMAKE_SOURCE_DIR}/ios/resources/Overte.entitlements"
      XCODE_ATTRIBUTE_ASSETCATALOG_COMPILER_APPICON_NAME "AppIcon"
      XCODE_ATTRIBUTE_IPHONEOS_DEPLOYMENT_TARGET "${CMAKE_OSX_DEPLOYMENT_TARGET}"
      XCODE_ATTRIBUTE_SUPPORTED_PLATFORMS "iphoneos iphonesimulator"
      XCODE_ATTRIBUTE_SUPPORTS_MACCATALYST "NO"
      XCODE_ATTRIBUTE_TARGETED_DEVICE_FAMILY "1,2"
      XCODE_ATTRIBUTE_PRODUCT_BUNDLE_IDENTIFIER "${OVERTE_IOS_BUNDLE_IDENTIFIER}"
    )
    if (OVERTE_IOS_ENABLE_SIGNING)
      set_target_properties(${TARGET_NAME} PROPERTIES
        XCODE_ATTRIBUTE_CODE_SIGN_STYLE "Automatic"
        XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "YES"
        XCODE_ATTRIBUTE_CODE_SIGNING_REQUIRED "YES"
        XCODE_ATTRIBUTE_DEVELOPMENT_TEAM "${OVERTE_IOS_DEVELOPMENT_TEAM}"
      )
    else()
      set_target_properties(${TARGET_NAME} PROPERTIES
        XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED "NO"
        XCODE_ATTRIBUTE_CODE_SIGNING_REQUIRED "NO"
      )
    endif()
    set(OVERTE_IOS_PRIVACY_MANIFEST "${CMAKE_SOURCE_DIR}/ios/resources/PrivacyInfo.xcprivacy")
    set(OVERTE_IOS_ASSET_CATALOG "${CMAKE_SOURCE_DIR}/ios/resources/Assets.xcassets")
    if (NOT EXISTS "${OVERTE_IOS_PRIVACY_MANIFEST}")
      message(FATAL_ERROR "The audited iOS PrivacyInfo.xcprivacy is required")
    endif()
    if (NOT EXISTS "${OVERTE_IOS_ASSET_CATALOG}/AppIcon.appiconset/Contents.json")
      message(FATAL_ERROR "The audited iOS AppIcon asset catalog is required")
    endif()
    target_sources(${TARGET_NAME} PRIVATE
      "${OVERTE_IOS_PRIVACY_MANIFEST}"
      "${OVERTE_IOS_ASSET_CATALOG}"
    )
    set_source_files_properties(
      "${OVERTE_IOS_PRIVACY_MANIFEST}"
      "${OVERTE_IOS_ASSET_CATALOG}"
      PROPERTIES
      MACOSX_PACKAGE_LOCATION Resources
    )
  else()
    set_target_properties(${TARGET_NAME} PROPERTIES
      MACOSX_BUNDLE_INFO_PLIST MacOSXBundleInfo.plist.in
    )
  endif()

  # make sure the output name for the .app bundle is correct
  # Fix up the rpath so macdeployqt works
  set_target_properties(${TARGET_NAME} PROPERTIES INSTALL_RPATH "@executable_path/../Frameworks")
elseif (WIN32)
  # configure an rc file for the chosen icon
  set(CONFIGURE_ICON_PATH "${CMAKE_CURRENT_SOURCE_DIR}/icon/${INTERFACE_ICON_FILENAME}")
  set(CONFIGURE_ICON_RC_OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/Icon.rc")
  configure_file("${HF_CMAKE_DIR}/templates/Icon.rc.in" ${CONFIGURE_ICON_RC_OUTPUT})

  set(APP_FULL_NAME "Overte")
  set(CONFIGURE_VERSION_INFO_RC_OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/VersionInfo.rc")
  configure_file("${HF_CMAKE_DIR}/templates/VersionInfo.rc.in" ${CONFIGURE_VERSION_INFO_RC_OUTPUT})

  # add an executable that also has the icon itself and the configured rc file as resources
  add_executable(${TARGET_NAME} WIN32 ${INTERFACE_SRCS} ${QM} ${CONFIGURE_ICON_RC_OUTPUT} ${CONFIGURE_VERSION_INFO_RC_OUTPUT})
  ##^^^^^ creates native Win32 app w/o cmd console vvvvvv forces cmd console for logging
  # add_executable(${TARGET_NAME} ${INTERFACE_SRCS} ${QM} ${CONFIGURE_ICON_RC_OUTPUT} ${CONFIGURE_VERSION_INFO_RC_OUTPUT})

  if (NOT DEV_BUILD)
    add_custom_command(
      TARGET ${TARGET_NAME}
      POST_BUILD
      COMMAND "mt.exe" -manifest "${CMAKE_CURRENT_SOURCE_DIR}/interface.exe.manifest" -inputresource:"$<TARGET_FILE:${TARGET_NAME}>"\;\#1 -outputresource:"$<TARGET_FILE:${TARGET_NAME}>"\;\#1
      COMMENT "Adding OS version support manifest to exe"
    )
  endif()

elseif (ANDROID)
  # on android the Interface target is a library that gets linked/used by the APK shell that qtcreateapk produces
  add_library(${TARGET_NAME} ${INTERFACE_SRCS} ${QM})
else ()
  add_executable(${TARGET_NAME} ${INTERFACE_SRCS} ${QM})
endif ()

if (NOT ANDROID)
  add_dependencies(${TARGET_NAME} resources)
endif()


if (WIN32)

  if (USE_SIXENSE)
    find_package(sixense QUIET REQUIRED)
    target_link_libraries(${TARGET_NAME} Sixense::Sixense)
  endif ()

  find_package(neuron QUIET REQUIRED)
  find_package(steamworks QUIET REQUIRED)
  target_link_libraries(${TARGET_NAME} Neuron::Datareader Steam::Works)
endif()

# disable /OPT:REF and /OPT:ICF for the Debug builds
# This will prevent the following linker warnings
# LINK : warning LNK4075: ignoring '/INCREMENTAL' due to '/OPT:ICF' specification
if (WIN32)
  set_property(TARGET ${TARGET_NAME} APPEND_STRING PROPERTY LINK_FLAGS_DEBUG "/OPT:NOREF /OPT:NOICF")
endif()

# link required hifi libraries
set(INTERFACE_GL_LIBRARY gl)
if(IOS AND OVERTE_RENDERING_BACKEND STREQUAL "Vulkan")
  # Interface has no direct GL consumer after the iOS source gates. VKWidget's
  # compatibility context remains an implementation detail of the vk target.
  set(INTERFACE_GL_LIBRARY "")
endif()
link_hifi_libraries(
  shared workload task octree ktx gpu ${INTERFACE_GL_LIBRARY} procedural graphics graphics-scripting render
  pointers recording hfm model-serializers networking material-networking
  model-networking model-baker entities avatars
  audio audio-client animation physics
  render-utils entities-renderer avatars-renderer ui qml ${INTERFACE_AUTO_UPDATER_LIBRARY} midi
  controllers plugins image platform
  ui-plugins display-plugins input-plugins
  # Platform specific GL libraries
  ${PLATFORM_GL_BACKEND}
  # Plaform specific input & display plugin libraries
  ${PLATFORM_PLUGIN_LIBRARIES}
  shaders
)
include_hifi_library_headers(script-engine)
include_hifi_library_headers(entities)
include_hifi_library_headers(render-utils)

# include the binary directory of render-utils for shader includes
target_include_directories(${TARGET_NAME} PRIVATE "${CMAKE_BINARY_DIR}/libraries/render-utils")

# include OpenSSL
target_openssl()

target_bullet()

set(OpenGL_GL_PREFERENCE "GLVND")
if(NOT IOS)
  target_opengl()
endif()
add_crashpad()
target_breakpad()
target_json()
target_glm()
if(NOT IOS)
  target_discord_rpc()
endif()
target_quazip()

# perform standard include and linking for found externals
foreach(EXTERNAL ${OPTIONAL_EXTERNALS})

  if (${${EXTERNAL}_UPPERCASE}_REQUIRED)
    find_package(${EXTERNAL} QUIET REQUIRED)
  else ()
    find_package(${EXTERNAL})
  endif ()

  if (${${EXTERNAL}_UPPERCASE}_FOUND AND NOT DISABLE_${${EXTERNAL}_UPPERCASE})
    add_definitions(-DHAVE_${${EXTERNAL}_UPPERCASE})

    # include the library directories (ignoring warnings)
    if (NOT ${${EXTERNAL}_UPPERCASE}_INCLUDE_DIRS)
      set(${${EXTERNAL}_UPPERCASE}_INCLUDE_DIRS ${${${EXTERNAL}_UPPERCASE}_INCLUDE_DIR})
    endif ()

    include_directories(SYSTEM ${${${EXTERNAL}_UPPERCASE}_INCLUDE_DIRS})

    # perform the system include hack for OS X to ignore warnings
    if (APPLE)
      foreach(EXTERNAL_INCLUDE_DIR  ${${${EXTERNAL}_UPPERCASE}_INCLUDE_DIRS})
        SET(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -isystem ${EXTERNAL_INCLUDE_DIR}")
      endforeach()
    endif ()

    if (NOT ${${EXTERNAL}_UPPERCASE}_LIBRARIES)
      set(${${EXTERNAL}_UPPERCASE}_LIBRARIES ${${${EXTERNAL}_UPPERCASE}_LIBRARY})
    endif ()

    if (NOT APPLE OR NOT ${${EXTERNAL}_UPPERCASE} MATCHES "SIXENSE")
      target_link_libraries(${TARGET_NAME} ${${${EXTERNAL}_UPPERCASE}_LIBRARIES})
    elseif (APPLE AND NOT INSTALLER_BUILD)
      add_definitions(-DSIXENSE_LIB_FILENAME=\"${${${EXTERNAL}_UPPERCASE}_LIBRARY_RELEASE}\")
    endif ()
  endif ()
endforeach()

# include headers for interface and InterfaceConfig.
target_include_directories(${TARGET_NAME} PRIVATE "${PROJECT_SOURCE_DIR}/src")

if (ANDROID)
  find_library(ANDROID_LOG_LIB log)
  target_link_libraries(${TARGET_NAME} ${ANDROID_LOG_LIB})
endif ()

overte_link_qt_modules(${TARGET_NAME}
  Gui Network Multimedia Widgets Qml Quick Svg WebChannel WebSockets)
if(NOT IOS)
  overte_link_qt_modules(${TARGET_NAME} WebEngineCore WebEngineWidgets)
endif()
target_link_libraries(${TARGET_NAME} ${PLATFORM_QT_LIBRARIES})

if (UNIX AND NOT ANDROID AND NOT OVERTE_THREAD_DEBUGGING)
    if (CMAKE_SYSTEM_NAME MATCHES "Linux")
        # Linux
        target_link_libraries(${TARGET_NAME} pthread atomic)
    else ()
        # OSX
        target_link_libraries(${TARGET_NAME} pthread)
    endif ()
endif()

# assume we are using a Qt build without bearer management
add_definitions(-DQT_NO_BEARERMANAGEMENT)

if (APPLE AND NOT IOS)
  # link in required OS X frameworks and include the right GL headers
  find_library(OpenGL OpenGL)
  find_library(AppKit AppKit)

  target_link_libraries(${TARGET_NAME} ${OpenGL} ${AppKit})

  # setup install of OS X interface bundle
  install(TARGETS ${TARGET_NAME}
    BUNDLE DESTINATION ${INTERFACE_INSTALL_DIR}
    COMPONENT ${CLIENT_COMPONENT}
  )

  set(SCRIPTS_INSTALL_DIR "${INTERFACE_INSTALL_APP_PATH}/Contents/Resources")
  set(RESOURCES_DEV_DIR "$<TARGET_FILE_DIR:${TARGET_NAME}>/../Resources")

  add_custom_command(TARGET ${TARGET_NAME} POST_BUILD
    # copy script files beside the executable
    COMMAND "${CMAKE_COMMAND}" -E copy_directory
      "${CMAKE_SOURCE_DIR}/scripts"
      "${RESOURCES_DEV_DIR}/scripts"
    # copy the resources files beside the executable
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
      "${RESOURCES_RCC}"
      "${RESOURCES_DEV_DIR}"
    # FIXME, the edit script code loads HTML from the scripts folder
    # which in turn relies on CSS that refers to the fonts.  In theory
    # we should be able to modify the CSS to reference the QRC path to
    # the ttf files, but doing so generates a CORS policy violation,
    # so we have to retain a copy of the fonts outside of the resources binary
    COMMAND "${CMAKE_COMMAND}" -E copy_directory
      "${PROJECT_SOURCE_DIR}/resources/fonts"
      "${RESOURCES_DEV_DIR}/fonts"
    #copy serverless for android
    COMMAND "${CMAKE_COMMAND}" -E copy_directory
      "${PROJECT_SOURCE_DIR}/resources/serverless"
      "${RESOURCES_DEV_DIR}/serverless"
    # add redirect json to macOS builds.
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
      "${PROJECT_SOURCE_DIR}/resources/serverless/redirect.json"
      "${RESOURCES_DEV_DIR}/serverless/redirect.json"
    )

  if (JSDOC_ENABLED)
    add_custom_command(TARGET ${TARGET_NAME} POST_BUILD
      # copy JSDoc files beside the executable
      COMMAND "${CMAKE_COMMAND}" -E copy_directory
      "${JSDOC_OUTPUT_PATH}"
      "${RESOURCES_DEV_DIR}/jsdoc")
  endif()
  # call the fixup_interface macro to add required bundling commands for installation
  fixup_interface()

else()
  set(INTERFACE_EXEC_DIR "$<TARGET_FILE_DIR:${TARGET_NAME}>")
  set(RESOURCES_DEV_DIR "${INTERFACE_EXEC_DIR}/resources")

  # copy the resources files beside the executable
  add_custom_command(TARGET ${TARGET_NAME} POST_BUILD
    # FIXME, the edit script code loads HTML from the scripts folder
    # which in turn relies on CSS that refers to the fonts.  In theory
    # we should be able to modify the CSS to reference the QRC path to
    # the ttf files, but doing so generates a CORS policy violation,
    # so we have to retain a copy of the fonts outside of the resources binary
    COMMAND "${CMAKE_COMMAND}" -E copy_directory
      "${PROJECT_SOURCE_DIR}/resources/fonts"
      "${RESOURCES_DEV_DIR}/fonts"
    COMMAND "${CMAKE_COMMAND}" -E copy_directory
      "${CMAKE_SOURCE_DIR}/scripts"
      "${INTERFACE_EXEC_DIR}/scripts"
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
      "${PROJECT_SOURCE_DIR}/resources/serverless/tutorial.json"
      "${RESOURCES_DEV_DIR}/serverless/tutorial.json"
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
      "${PROJECT_SOURCE_DIR}/resources/serverless/redirect.json"
      "${RESOURCES_DEV_DIR}/serverless/redirect.json"
    COMMAND "${CMAKE_COMMAND}" -E copy_if_different
      "${RESOURCES_RCC}"
      "${INTERFACE_EXEC_DIR}/resources.rcc"
  )

  if (JSDOC_ENABLED)
    add_custom_command(TARGET ${TARGET_NAME} POST_BUILD
    # copy JSDoc files beside the executable
    COMMAND "${CMAKE_COMMAND}" -E copy_directory
      "${JSDOC_OUTPUT_PATH}"
      "${INTERFACE_EXEC_DIR}/jsdoc")
  endif()

  # link target to external libraries
  if (WIN32)
    target_link_libraries(${TARGET_NAME} wsock32.lib Winmm.lib)

    # setup install of executable and things copied by fixup/windeployqt
    install(
      DIRECTORY "$<TARGET_FILE_DIR:${TARGET_NAME}>/"
      DESTINATION ${INTERFACE_INSTALL_DIR}
      COMPONENT ${CLIENT_COMPONENT}
      PATTERN "*.pdb" EXCLUDE
      PATTERN "*.lib" EXCLUDE
      PATTERN "*.exp" EXCLUDE
    )

    set(SCRIPTS_INSTALL_DIR "${INTERFACE_INSTALL_DIR}")

    set(EXECUTABLE_COMPONENT ${CLIENT_COMPONENT})

    optional_win_executable_signing()
  endif()
endif()

if (SCRIPTS_INSTALL_DIR)
  # setup install of scripts beside interface executable
  install(
    DIRECTORY "${CMAKE_SOURCE_DIR}/scripts/"
    DESTINATION ${SCRIPTS_INSTALL_DIR}/scripts
    COMPONENT ${CLIENT_COMPONENT}
  )
endif()

if (OVERTE_DOWNLOAD_SERVERLESS_CONTENT)
  add_dependency_external_projects(serverless-content)

  ExternalProject_Get_Property(serverless-content SOURCE_DIR)

  # for dev builds, copy the serverless content to the resources folder
  add_custom_command(TARGET ${TARGET_NAME} POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E copy_directory
      "${SOURCE_DIR}"
      "${RESOURCES_DEV_DIR}/serverless"
  )
endif ()

set(EXTRA_DEPLOY_OPTIONS "--qmldir  \"${PROJECT_SOURCE_DIR}/resources/qml\"")

set(TARGET_INSTALL_DIR ${INTERFACE_INSTALL_DIR})
set(TARGET_INSTALL_COMPONENT ${CLIENT_COMPONENT})
manually_install_openssl_for_qt()
package_libraries_for_deployment()

if(OVERTE_USE_SYSTEM_LIBS)
    find_path(GIFCREATOR_INCLUDE_DIRS "GifCreator/GifCreator.h")
    target_include_directories(${TARGET_NAME} SYSTEM PRIVATE ${GIFCREATOR_INCLUDE_DIRS} "${GIFCREATOR_INCLUDE_DIRS}/GifCreator")
else()
    find_package(GifCreator QUIET REQUIRED)
    target_link_libraries(${TARGET_NAME} GifCreator::GifCreator)
endif()

# tell CMake to exclude ui_console.h for policy CMP0071
set_property(SOURCE ui_console.h PROPERTY SKIP_AUTOMOC ON)
