#
#  FixupInterface.cmake
#  cmake/macros
#
#  Copyright 2016 High Fidelity, Inc.
#  Copyright 2025 Overte e.V.
#  Created by Stephen Birarda on January 6th, 2016
#
#  Distributed under the Apache License, Version 2.0.
#  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
#

function(overte_find_macdeployqt output_variable)
    set(_qt_bin_hints "")

    # Qt's config packages are the most reliable source in Conan/aqt builds:
    # QT_DIR is not part of Qt's CMake contract, while Qt5Core_DIR and
    # Qt6Core_DIR point to <qt-prefix>/lib/cmake/Qt*Core.
    foreach(_qt_core_dir IN ITEMS "${Qt5Core_DIR}" "${Qt6Core_DIR}")
        if (_qt_core_dir)
            get_filename_component(_qt_prefix "${_qt_core_dir}/../../.." ABSOLUTE)
            list(APPEND _qt_bin_hints "${_qt_prefix}/bin")
        endif()
    endforeach()

    foreach(_qt_prefix IN ITEMS "${QT_DIR}" "${QT_HOST_PATH}")
        if (_qt_prefix)
            list(APPEND _qt_bin_hints "${_qt_prefix}/bin")
        endif()
    endforeach()

    foreach(_qt_prefix IN LISTS CMAKE_PREFIX_PATH)
        list(APPEND _qt_bin_hints
            "${_qt_prefix}/bin"
            "${_qt_prefix}/../bin"
            "${_qt_prefix}/../../bin"
        )
    endforeach()

    # Imported Core targets cover non-standard package layouts. Walk their
    # library ancestors because a framework binary can be several levels below
    # the Qt prefix, unlike a regular lib/QtCore.dylib.
    foreach(_qt_core_target IN ITEMS Qt5::Core Qt6::Core)
        if (TARGET "${_qt_core_target}")
            get_target_property(_qt_core_location "${_qt_core_target}" IMPORTED_LOCATION)
            if (NOT _qt_core_location)
                foreach(_qt_config IN ITEMS RELEASE RELWITHDEBINFO MINSIZEREL DEBUG)
                    get_target_property(_qt_core_location "${_qt_core_target}"
                        "IMPORTED_LOCATION_${_qt_config}")
                    if (_qt_core_location)
                        break()
                    endif()
                endforeach()
            endif()
            if (_qt_core_location)
                get_filename_component(_qt_location_parent "${_qt_core_location}" DIRECTORY)
                foreach(_unused RANGE 0 7)
                    list(APPEND _qt_bin_hints "${_qt_location_parent}/bin")
                    get_filename_component(_qt_location_parent "${_qt_location_parent}" DIRECTORY)
                endforeach()
            endif()
        endif()
    endforeach()

    list(REMOVE_DUPLICATES _qt_bin_hints)
    unset(_overte_macdeployqt CACHE)
    find_program(_overte_macdeployqt macdeployqt
        HINTS ${_qt_bin_hints}
        NO_DEFAULT_PATH
    )
    set(${output_variable} "${_overte_macdeployqt}" PARENT_SCOPE)
    unset(_overte_macdeployqt CACHE)
endfunction()

macro(fixup_interface)
    if (APPLE)
        string(REPLACE " " "\\ " ESCAPED_BUNDLE_NAME ${INTERFACE_BUNDLE_NAME})
        string(REPLACE " " "\\ " ESCAPED_INSTALL_PATH ${INTERFACE_INSTALL_DIR})
        set(_INTERFACE_INSTALL_PATH "${ESCAPED_INSTALL_PATH}/${ESCAPED_BUNDLE_NAME}.app")

        overte_find_macdeployqt(MACDEPLOYQT_COMMAND)

        if (NOT MACDEPLOYQT_COMMAND)
            message(FATAL_ERROR "Could not find macdeployqt for the selected Qt installation.\
                It is required to produce an relocatable interface application.\
                Check Qt5Core_DIR/Qt6Core_DIR, QT_HOST_PATH, QT_DIR, and CMAKE_PREFIX_PATH.\
            ")
        endif ()

        if (OVERTE_RELEASE_TYPE STREQUAL "DEV")
            # A developer build is launched directly from the build tree by
            # local workflows and smoke tests.  Make that bundle relocatable;
            # the install-time deployment below only covers `cmake --install`.
            add_custom_command(TARGET ${TARGET_NAME} POST_BUILD
                COMMAND ${MACDEPLOYQT_COMMAND} "$<TARGET_FILE_DIR:${TARGET_NAME}>/../.." -verbose=2 -qmldir=${CMAKE_SOURCE_DIR}/interface/resources/qml/
            )
            install(CODE "
                execute_process(COMMAND ${MACDEPLOYQT_COMMAND}\
                    \${CMAKE_INSTALL_PREFIX}/${_INTERFACE_INSTALL_PATH}/\
                    -verbose=2 -qmldir=${CMAKE_SOURCE_DIR}/interface/resources/qml/\
                )"
                COMPONENT ${CLIENT_COMPONENT}
            )
        else ()
            add_custom_command(TARGET ${TARGET_NAME} POST_BUILD
                COMMAND ${MACDEPLOYQT_COMMAND} "$<TARGET_FILE_DIR:${TARGET_NAME}>/../.." -verbose=2 -qmldir=${CMAKE_SOURCE_DIR}/interface/resources/qml/
            )
        endif()
    endif ()
endmacro()
