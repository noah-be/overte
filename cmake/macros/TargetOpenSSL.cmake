#
#  Copyright 2015 High Fidelity, Inc.
#  Copyright 2025-2026 Overte e.V.
#  Created by Bradley Austin Davis on 2015/10/10
#
#  Distributed under the Apache License, Version 2.0.
#  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
#
macro(TARGET_OPENSSL)
    find_package(OpenSSL QUIET REQUIRED)
    if (TARGET OpenSSL::SSL AND TARGET OpenSSL::Crypto)
        target_link_libraries(${TARGET_NAME} OpenSSL::SSL OpenSSL::Crypto)
    elseif (TARGET openssl::openssl)
        # The pinned source-only Conan provider exports one aggregate target
        # carrying both canonical Android libraries and their system links.
        target_link_libraries(${TARGET_NAME} openssl::openssl)
    else()
        message(FATAL_ERROR "OpenSSL provider exports no supported CMake target")
    endif()
endmacro()
