cmake_minimum_required(VERSION 3.16)

project(overte_android_native_tests LANGUAGES CXX)

include(CTest)

if(NOT BUILD_TESTING)
    return()
endif()

set(OVERTE_INTERFACE_UI_DIR
    "${CMAKE_CURRENT_LIST_DIR}/../../../interface/src/ui"
    CACHE PATH
    "Path to the Overte interface UI headers")

if(NOT EXISTS "${OVERTE_INTERFACE_UI_DIR}/PhoneLoginState.h")
    message(FATAL_ERROR
        "PhoneLoginState.h was not found below OVERTE_INTERFACE_UI_DIR: "
        "${OVERTE_INTERFACE_UI_DIR}")
endif()

add_library(overte_native_test_options INTERFACE)
target_compile_features(overte_native_test_options INTERFACE cxx_std_11)
target_include_directories(overte_native_test_options INTERFACE
    "${OVERTE_INTERFACE_UI_DIR}"
    "${CMAKE_CURRENT_LIST_DIR}/../../apps/phoneInterface/src"
    "${CMAKE_CURRENT_LIST_DIR}/support")
target_include_directories(overte_native_test_options INTERFACE
    "${CMAKE_CURRENT_LIST_DIR}/../../apps/picoInterface/openxr/src")

if(MSVC)
    target_compile_options(overte_native_test_options INTERFACE /W4 /WX)
else()
    target_compile_options(overte_native_test_options INTERFACE
        -UNDEBUG
        -Wall
        -Wextra
        -Wpedantic
        -Werror)
endif()

function(add_overte_native_test target source)
    add_executable("${target}" "${source}")
    target_link_libraries("${target}" PRIVATE overte_native_test_options)
    add_test(NAME "${target}" COMMAND "${target}")
    set_tests_properties("${target}" PROPERTIES
        TIMEOUT 10
        LABELS "native;host")
endfunction()

# Keep the original regression contract as a first-class CTest target. This
# prevents the CMake suite and the legacy shell runner from silently diverging.
add_overte_native_test(
    phone_login_state_contract
    "${CMAKE_CURRENT_LIST_DIR}/../phone-login-state-contract-test.cpp")
if(MSVC)
    target_compile_options(phone_login_state_contract PRIVATE /UNDEBUG)
else()
    target_compile_options(phone_login_state_contract PRIVATE -UNDEBUG)
endif()

add_overte_native_test(
    phone_login_state_transitions
    "${CMAKE_CURRENT_LIST_DIR}/phone_login_state_transitions_test.cpp")

add_overte_native_test(
    phone_login_state_instances
    "${CMAKE_CURRENT_LIST_DIR}/phone_login_state_instances_test.cpp")

add_overte_native_test(
    phone_login_state_deterministic_properties
    "${CMAKE_CURRENT_LIST_DIR}/phone_login_state_property_test.cpp")

add_overte_native_test(
    phone_graphics_bool_policy
    "${CMAKE_CURRENT_LIST_DIR}/phone_graphics_bool_policy_test.cpp")

add_overte_native_test(
    phone_graphics_float_policy
    "${CMAKE_CURRENT_LIST_DIR}/phone_graphics_float_policy_test.cpp")

add_overte_native_test(
    phone_graphics_unsigned_policy
    "${CMAKE_CURRENT_LIST_DIR}/phone_graphics_unsigned_policy_test.cpp")

add_overte_native_test(
    phone_graphics_deterministic_properties
    "${CMAKE_CURRENT_LIST_DIR}/phone_graphics_property_test.cpp")

add_overte_native_test(
    phone_pending_handoff_lifecycle
    "${CMAKE_CURRENT_LIST_DIR}/phone_pending_handoff_lifecycle_test.cpp")

add_overte_native_test(
    phone_pending_handoff_replacement
    "${CMAKE_CURRENT_LIST_DIR}/phone_pending_handoff_replacement_test.cpp")

add_overte_native_test(
    phone_pending_handoff_move
    "${CMAKE_CURRENT_LIST_DIR}/phone_pending_handoff_move_test.cpp")

set(OVERTE_BUNDLED_JDK_ROOT
    "${CMAKE_CURRENT_LIST_DIR}/../../pico-host-tools/jdk-21"
    CACHE PATH "Optional repository-local JDK used for JNI test headers")
set(OVERTE_JNI_HINTS
    "$ENV{JAVA_HOME}/include"
    "${OVERTE_BUNDLED_JDK_ROOT}/include")
find_program(OVERTE_JAVAC_EXECUTABLE javac)
if(OVERTE_JAVAC_EXECUTABLE)
    execute_process(
        COMMAND "${OVERTE_JAVAC_EXECUTABLE}" -J-XshowSettings:properties -version
        OUTPUT_VARIABLE OVERTE_JAVA_PROPERTIES
        ERROR_VARIABLE OVERTE_JAVA_PROPERTIES
        RESULT_VARIABLE OVERTE_JAVAC_PROPERTIES_STATUS)
    if(OVERTE_JAVAC_PROPERTIES_STATUS EQUAL 0 AND
            OVERTE_JAVA_PROPERTIES MATCHES "java.home = ([^\r\n]+)")
        string(STRIP "${CMAKE_MATCH_1}" OVERTE_DISCOVERED_JAVA_HOME)
        list(APPEND OVERTE_JNI_HINTS "${OVERTE_DISCOVERED_JAVA_HOME}/include")
        # Java 8 reports the nested JRE as java.home, while newer JDKs report
        # the JDK root itself.
        list(APPEND OVERTE_JNI_HINTS "${OVERTE_DISCOVERED_JAVA_HOME}/../include")
    endif()
endif()
find_path(OVERTE_JNI_INCLUDE_DIR jni.h HINTS ${OVERTE_JNI_HINTS})
if(NOT OVERTE_JNI_INCLUDE_DIR)
    message(FATAL_ERROR
        "jni.h is required for the production JNI compatibility test. "
        "Install a JDK, export JAVA_HOME, or pass -DOVERTE_JNI_INCLUDE_DIR=<jdk>/include.")
endif()
if(WIN32)
    set(OVERTE_JNI_PLATFORM_SUBDIR win32)
elseif(APPLE)
    set(OVERTE_JNI_PLATFORM_SUBDIR darwin)
else()
    set(OVERTE_JNI_PLATFORM_SUBDIR linux)
endif()

add_overte_native_test(
    qt_input_connection_compat
    "${CMAKE_CURRENT_LIST_DIR}/qt_input_connection_compat_test.cpp")
target_sources(qt_input_connection_compat PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/../../shared/src/QtInputConnectionCompat.cpp")
target_include_directories(qt_input_connection_compat PRIVATE
    "${OVERTE_JNI_INCLUDE_DIR}"
    "${OVERTE_JNI_INCLUDE_DIR}/${OVERTE_JNI_PLATFORM_SUBDIR}")

add_overte_native_test(
    phone_pending_handoff_deterministic_properties
    "${CMAKE_CURRENT_LIST_DIR}/phone_pending_handoff_property_test.cpp")

add_overte_native_test(
    pico_openxr_debug_policy
    "${CMAKE_CURRENT_LIST_DIR}/pico_openxr_debug_policy_test.cpp")

add_overte_native_test(
    pico_openxr_input_policy
    "${CMAKE_CURRENT_LIST_DIR}/pico_openxr_input_policy_test.cpp")

add_overte_native_test(
    pico_openxr_space_policy
    "${CMAKE_CURRENT_LIST_DIR}/pico_openxr_space_policy_test.cpp")

add_overte_native_test(
    pico_openxr_display_policy
    "${CMAKE_CURRENT_LIST_DIR}/pico_openxr_display_policy_test.cpp")

add_overte_native_test(
    pico_openxr_graphics_policy
    "${CMAKE_CURRENT_LIST_DIR}/pico_openxr_graphics_policy_test.cpp")

add_overte_native_test(
    pico_openxr_extension_policy
    "${CMAKE_CURRENT_LIST_DIR}/pico_openxr_extension_policy_test.cpp")

add_overte_native_test(
    pico_openxr_event_policy
    "${CMAKE_CURRENT_LIST_DIR}/pico_openxr_event_policy_test.cpp")

set_tests_properties(
    pico_openxr_debug_policy
    pico_openxr_input_policy
    pico_openxr_space_policy
    pico_openxr_display_policy
    pico_openxr_graphics_policy
    pico_openxr_extension_policy
    pico_openxr_event_policy
    PROPERTIES LABELS "native;host;android-vr")
