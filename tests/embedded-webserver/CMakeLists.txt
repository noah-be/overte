# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

# A focused Qt host build still compiles every embedded-webserver product source.
# Normal Overte builds use the existing product library target.

macro(setup_testcase_dependencies)
  if(OVERTE_WEBSERVER_STANDALONE)
    target_link_libraries(${TARGET_NAME} embedded-webserver)
  else()
    link_hifi_libraries(embedded-webserver)
    package_libraries_for_deployment()
  endif()
endmacro()

setup_hifi_testcase(Network)
if(TARGET embedded-webserver-HTTPManagerTests)
  set_tests_properties(embedded-webserver-HTTPManagerTests-test PROPERTIES
    TIMEOUT 120 LABELS "native-ci;embedded-webserver")
endif()
