# Declare dependencies
macro (setup_testcase_dependencies)
  # link in the shared libraries
  link_hifi_libraries(shared test-utils ktx gpu gl image shaders networking ${PLATFORM_GL_BACKEND})
  package_libraries_for_deployment()
  target_opengl()
  target_zlib()
  target_quazip()
  if("${TARGET_NAME}" STREQUAL "gpu-TextureTest")
    file(INSTALL "${CMAKE_SOURCE_DIR}/scripts/developer/tests/cube_texture.png"
      DESTINATION "${CMAKE_CURRENT_BINARY_DIR}")
  endif()
#  if (WIN32)
#    add_dependency_external_projects(wasapi)
#  endif ()
endmacro ()
set(OpenGL_GL_PREFERENCE "GLVND")
setup_hifi_testcase()
