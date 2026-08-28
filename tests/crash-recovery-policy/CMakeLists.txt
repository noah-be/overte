if (CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    cmake_minimum_required(VERSION 3.22)
    project(crash-recovery-policy-tests LANGUAGES CXX)

    set(CMAKE_AUTOMOC ON)
    set(CMAKE_CXX_STANDARD 17)
    set(CMAKE_CXX_STANDARD_REQUIRED ON)

    find_package(QT NAMES Qt6 Qt5 REQUIRED COMPONENTS Test)
    find_package(Qt${QT_VERSION_MAJOR} REQUIRED COMPONENTS Test)

    add_executable(crash-recovery-policy-CrashRecoveryPolicyTests
        src/CrashRecoveryPolicyTests.cpp)
    target_include_directories(crash-recovery-policy-CrashRecoveryPolicyTests PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/../../interface/src")
    target_link_libraries(crash-recovery-policy-CrashRecoveryPolicyTests PRIVATE
        Qt${QT_VERSION_MAJOR}::Test)

    enable_testing()
    add_test(NAME crash-recovery-policy-CrashRecoveryPolicyTests-test
        COMMAND crash-recovery-policy-CrashRecoveryPolicyTests)

    add_executable(crash-recovery-policy-IosPlatformMappingTests
        src/CrashRecoveryPolicyTests.cpp)
    target_compile_definitions(crash-recovery-policy-IosPlatformMappingTests PRIVATE Q_OS_IOS)
    target_include_directories(crash-recovery-policy-IosPlatformMappingTests PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/../../interface/src")
    target_link_libraries(crash-recovery-policy-IosPlatformMappingTests PRIVATE
        Qt${QT_VERSION_MAJOR}::Test)
    add_test(NAME crash-recovery-policy-IosPlatformMappingTests-test
        COMMAND crash-recovery-policy-IosPlatformMappingTests)
else ()
    macro (setup_testcase_dependencies)
        target_include_directories(${TARGET_NAME} PRIVATE "${PROJECT_SOURCE_DIR}/interface/src")
    endmacro ()

    setup_hifi_testcase()
endif ()
