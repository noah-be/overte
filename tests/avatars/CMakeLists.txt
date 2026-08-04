# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

macro (setup_testcase_dependencies)
  link_hifi_libraries(shared test-utils networking script-engine avatars)

  package_libraries_for_deployment()
endmacro ()

setup_hifi_testcase(Network)
