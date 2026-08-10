set(TARGET_NAME platform)

setup_hifi_library()
link_hifi_libraries(shared gl)

if (IOS)
  # Q_OS_MAC may also be visible for Darwin-family targets. Never compile the
  # AppKit/ApplicationServices/CGL backend into the closed iOS application.
  get_target_property(PLATFORM_TARGET_SOURCES ${TARGET_NAME} SOURCES)
  list(REMOVE_ITEM PLATFORM_TARGET_SOURCES
    "${CMAKE_CURRENT_SOURCE_DIR}/src/platform/backend/MACOSPlatform.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/platform/backend/MACOSPlatform.h")
else()
  get_target_property(PLATFORM_TARGET_SOURCES ${TARGET_NAME} SOURCES)
  list(REMOVE_ITEM PLATFORM_TARGET_SOURCES
    "${CMAKE_CURRENT_SOURCE_DIR}/src/platform/backend/IOSPlatform.cpp"
    "${CMAKE_CURRENT_SOURCE_DIR}/src/platform/backend/IOSPlatform.h")
endif()
set_property(TARGET ${TARGET_NAME} PROPERTY SOURCES ${PLATFORM_TARGET_SOURCES})

GroupSources("src")
target_json()

if (APPLE AND NOT IOS)
  # link in required OS X frameworks and include the right GL headers
  find_library(OpenGL OpenGL)
  find_library(AppKit AppKit)

  target_link_libraries(${TARGET_NAME} ${OpenGL} ${AppKit})

elseif(WIN32)
    target_link_libraries(${TARGET_NAME} Iphlpapi.lib)
endif()
