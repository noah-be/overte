# Copyright 2023 Overte contributors
# Copyright 2023 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set(TARGET_NAME JSAPIExample)
setup_hifi_client_server_plugin(scripting)
overte_find_qt(COMPONENTS Core Core5Compat QUIET REQUIRED)
overte_link_qt_modules(${TARGET_NAME} Core5Compat)
link_hifi_libraries(shared plugins script-engine)
include_hifi_library_headers(networking)
