set(TARGET_NAME qml)
setup_hifi_library(Multimedia Network Qml Quick WebChannel WebSockets ${PLATFORM_QT_COMPONENTS})
link_hifi_libraries(shared networking gl)

# Required for some low level GL interaction in the OffscreenQMLSurface
set(OpenGL_GL_PREFERENCE "GLVND")
target_opengl()

# The Phone fatal snapshot reads the matching Qt package's private frame layout.
if (ANDROID AND HIFI_ANDROID_APP STREQUAL "phoneInterface")
    # Conan exposes the recipe suffix in Qt5_VERSION_STRING, while Qt installs
    # private headers under the upstream numeric version. Its generated private
    # targets can therefore refer to a directory that does not exist.
    string(REGEX MATCH "^[0-9]+\\.[0-9]+\\.[0-9]+" PHONE_QML_QT_HEADER_VERSION
        "${Qt5_VERSION_STRING}")
    if (NOT PHONE_QML_QT_HEADER_VERSION)
        message(FATAL_ERROR "Phone QML diagnostics require the selected Qt package version")
    endif()
    foreach(PHONE_QML_QT_MODULE Core Qml)
        if (PHONE_QML_QT_MODULE STREQUAL "Core")
            set(PHONE_QML_PRIVATE_MARKER "qglobal_p.h")
        else()
            set(PHONE_QML_PRIVATE_MARKER "qqmlengine_p.h")
        endif()
        set(PHONE_QML_PRIVATE_MODULE_DIR "")
        foreach(PHONE_QML_QT_INCLUDE IN LISTS Qt5_INCLUDE_DIRS)
            foreach(PHONE_QML_QT_CANDIDATE
                    "${PHONE_QML_QT_INCLUDE}/Qt${PHONE_QML_QT_MODULE}/${PHONE_QML_QT_HEADER_VERSION}/Qt${PHONE_QML_QT_MODULE}"
                    "${PHONE_QML_QT_INCLUDE}/${PHONE_QML_QT_HEADER_VERSION}/Qt${PHONE_QML_QT_MODULE}")
                if (EXISTS "${PHONE_QML_QT_CANDIDATE}/private/${PHONE_QML_PRIVATE_MARKER}")
                    set(PHONE_QML_PRIVATE_MODULE_DIR "${PHONE_QML_QT_CANDIDATE}")
                    break()
                endif()
            endforeach()
            if (PHONE_QML_PRIVATE_MODULE_DIR)
                break()
            endif()
        endforeach()
        if (NOT PHONE_QML_PRIVATE_MODULE_DIR)
            message(FATAL_ERROR "Phone QML diagnostics cannot locate matching Qt${PHONE_QML_QT_MODULE} private headers")
        endif()
        get_filename_component(PHONE_QML_PRIVATE_VERSION_DIR
            "${PHONE_QML_PRIVATE_MODULE_DIR}" DIRECTORY)
        target_include_directories(${TARGET_NAME} PRIVATE
            "${PHONE_QML_PRIVATE_VERSION_DIR}" "${PHONE_QML_PRIVATE_MODULE_DIR}")
    endforeach()
endif()
