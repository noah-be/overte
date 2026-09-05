# Neutral Android toolchain contract shared by Phone and Pico consumers.
# The caller must materialize the declared tool roots; no host fallback is used.

cmake_minimum_required(VERSION 3.24)

foreach(_required_environment ANDROID_SDK_ROOT ANDROID_NDK_HOME JAVA_HOME)
    if(NOT DEFINED ENV{${_required_environment}} OR "$ENV{${_required_environment}}" STREQUAL "")
        message(FATAL_ERROR "${_required_environment} must be supplied by the verified base toolchain")
    endif()
endforeach()

set(CMAKE_SYSTEM_NAME Android CACHE STRING "" FORCE)
set(CMAKE_SYSTEM_VERSION 26 CACHE STRING "" FORCE)
set(CMAKE_ANDROID_API 26 CACHE STRING "" FORCE)
set(CMAKE_ANDROID_ARCH_ABI arm64-v8a CACHE STRING "" FORCE)
set(CMAKE_ANDROID_ARCH arm64 CACHE STRING "" FORCE)
set(CMAKE_ANDROID_NDK "$ENV{ANDROID_NDK_HOME}" CACHE PATH "" FORCE)
set(CMAKE_ANDROID_STL_TYPE c++_shared CACHE STRING "" FORCE)

set(_overte_android_compile_flags "-D__BIONIC_NO_PAGE_SIZE_MACRO")
set(_overte_android_link_flags "-Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384")

set(CMAKE_C_FLAGS_INIT "${_overte_android_compile_flags}")
set(CMAKE_CXX_FLAGS_INIT "${_overte_android_compile_flags}")
set(CMAKE_EXE_LINKER_FLAGS_INIT "${_overte_android_link_flags}")
set(CMAKE_SHARED_LINKER_FLAGS_INIT "${_overte_android_link_flags}")
set(CMAKE_MODULE_LINKER_FLAGS_INIT "${_overte_android_link_flags}")

unset(_overte_android_compile_flags)
unset(_overte_android_link_flags)
unset(_required_environment)
