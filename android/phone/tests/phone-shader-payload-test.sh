#!/usr/bin/env bash
set -euo pipefail

android_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
repo_root="$(cd "${android_dir}/.." && pwd)"
autoscribe="${repo_root}/cmake/macros/AutoScribeShader.cmake"
shader_cmake="${repo_root}/libraries/shaders/CMakeLists.txt"
shaders_cpp="${repo_root}/libraries/shaders/src/shaders/Shaders.cpp.in"

require() {
    local file="$1"
    local pattern="$2"
    local message="$3"
    if ! grep -Eq -- "$pattern" "$file"; then
        echo "FAIL: ${message}" >&2
        exit 1
    fi
}

require_block() {
    local file="$1"
    local pattern="$2"
    local message="$3"
    if ! PHONE_SHADER_TEST_PATTERN="$pattern" \
        perl -0ne '$found = 1 if /$ENV{PHONE_SHADER_TEST_PATTERN}/s; END { exit !$found }' "$file"; then
        echo "FAIL: ${message}" >&2
        exit 1
    fi
}

require "$shader_cmake" 'if \(HIFI_ANDROID AND HIFI_ANDROID_APP STREQUAL "phoneInterface"\)' \
    'phone shader definition is not scoped to Android phoneInterface'
require "$shader_cmake" 'target_compile_definitions\(\$\{TARGET_NAME\} PRIVATE OVERTE_ANDROID_PHONE_SHADER_PAYLOAD\)' \
    'phone shader payload compile definition is missing'
require "$shaders_cpp" '#if defined\(OVERTE_ANDROID_PHONE_SHADER_PAYLOAD\)' \
    'runtime variant selection is not guarded by the phone definition'
require "$shaders_cpp" 'ALL_VARIANTS\{ \{ Variant::Mono \} \}' \
    'phone runtime variant list is not mono-only'
require "$shaders_cpp" 'ALL_VARIANTS\{ \{ Variant::Mono, Variant::Stereo \} \}' \
    'non-phone runtime variant list was removed'

require "$autoscribe" 'if \(NOT \(HIFI_ANDROID AND HIFI_ANDROID_APP STREQUAL "phoneInterface"\)\)' \
    'shader generation does not retain a non-phone branch'
require "$autoscribe" 'AUTOSCRIBE_PLATFORM_SHADER\("310es"\)' \
    'mono GLES shader generation is missing'
require "$autoscribe" 'AUTOSCRIBE_PLATFORM_SHADER\("310es/stereo"\)' \
    'non-phone stereo GLES generation was removed'
require "$autoscribe" 'AUTOSCRIBE_PLATFORM_SHADER\("410"\)' \
    'non-phone GLSL 4.10 generation was removed'
require "$autoscribe" 'AUTOSCRIBE_PLATFORM_SHADER\("450"\)' \
    'non-phone GLSL 4.50 generation was removed'
require "$autoscribe" 'AUTOSCRIBE_DIALECT STREQUAL "310es" AND AUTOSCRIBE_VARIANT STREQUAL "mono"' \
    'phone QRC payload is not constrained to mono GLES'

# Validate the payload aliases separately from the generated intermediate
# artifacts: phone packages scribe and reflection, never SPIR-V or GLSL.
require "$autoscribe" 'AUTOSCRIBE_APPEND_QRC\("\$\{SHADER_COUNT\}/\$\{AUTOSCRIBE_PLATFORM_PATH\}/scribe"' \
    'scribed shader QRC entry is missing'
require "$autoscribe" 'AUTOSCRIBE_APPEND_QRC\("\$\{SHADER_COUNT\}/\$\{AUTOSCRIBE_PLATFORM_PATH\}/json"' \
    'reflection QRC entry is missing'
require_block "$autoscribe" 'if \(NOT \(HIFI_ANDROID AND HIFI_ANDROID_APP STREQUAL "phoneInterface"\)\).*?AUTOSCRIBE_APPEND_QRC\("\$\{SHADER_COUNT\}/\$\{AUTOSCRIBE_PLATFORM_PATH\}/spirv"' \
    'SPIR-V QRC entry is not excluded from phone packaging'
require_block "$autoscribe" 'if \(NOT \(HIFI_ANDROID AND HIFI_ANDROID_APP STREQUAL "phoneInterface"\)\).*?AUTOSCRIBE_APPEND_QRC\("\$\{SHADER_COUNT\}/\$\{AUTOSCRIBE_PLATFORM_PATH\}/glsl"' \
    'GLSL QRC entry is not excluded from phone packaging'

echo 'Android phone shader payload checks passed.'
