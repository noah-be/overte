# Declare dependencies
macro (setup_testcase_dependencies)
  link_hifi_libraries(shared test-utils)
  include_hifi_library_headers(entities-renderer)
  package_libraries_for_deployment()
endmacro ()

setup_hifi_testcase()
