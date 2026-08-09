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
    phone_graphics_bool_policy
    "${CMAKE_CURRENT_LIST_DIR}/phone_graphics_bool_policy_test.cpp")

add_overte_native_test(
    phone_graphics_float_policy
    "${CMAKE_CURRENT_LIST_DIR}/phone_graphics_float_policy_test.cpp")

add_overte_native_test(
    phone_graphics_unsigned_policy
    "${CMAKE_CURRENT_LIST_DIR}/phone_graphics_unsigned_policy_test.cpp")

add_overte_native_test(
    phone_pending_handoff_lifecycle
    "${CMAKE_CURRENT_LIST_DIR}/phone_pending_handoff_lifecycle_test.cpp")

add_overte_native_test(
    phone_pending_handoff_replacement
    "${CMAKE_CURRENT_LIST_DIR}/phone_pending_handoff_replacement_test.cpp")

add_overte_native_test(
    phone_pending_handoff_move
    "${CMAKE_CURRENT_LIST_DIR}/phone_pending_handoff_move_test.cpp")
