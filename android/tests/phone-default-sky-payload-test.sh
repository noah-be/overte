#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
android_dir="$(cd -- "$script_dir/.." && pwd)"
repo_root="$(cd -- "$android_dir/.." && pwd)"
interface_cmake="$repo_root/interface/CMakeLists.txt"
generate_qrc="$repo_root/cmake/macros/GenerateQrc.cmake"
texture_cache="$repo_root/libraries/material-networking/src/material-networking/TextureCache.cpp"
phone_defaults="$repo_root/scripts/+android_phoneInterface/defaultScripts.js"

grep -q 'multiValueArgs CUSTOM_PATHS GLOBS EXCLUDES' "$generate_qrc"
grep -q 'foreach(EXCLUDE_PATTERN.*GENERATE_QRC_EXCLUDES' "$generate_qrc"
grep -q 'if (HIFI_ANDROID AND HIFI_ANDROID_APP STREQUAL "phoneInterface")' "$interface_cmake"
grep -Fq 'Default-Sky-9-cubemap(-ambient)?[.]ktx$' "$interface_cmake"
grep -Fq '^meshes/controller/.*' "$interface_cmake"
grep -q 'EXCLUDES.*INTERFACE_QRC_EXCLUDES' "$interface_cmake"
grep -Fq 'system/+android_interface/touchscreenvirtualpad.js' "$phone_defaults"
if grep -Eq '(vive|touch)ControllerConfiguration[.]js|controllerScripts[.]js' "$phone_defaults"; then
    echo 'phone defaults unexpectedly load a VR controller-model script' >&2
    exit 1
fi

# Android must retain its compressed-format selection and original fallback;
# only the compile-time-disabled uncompressed branch may be removed.
awk '
    /for \(auto pair : meta.availableTextureTypes\)/ { compressed=1 }
    compressed && /backend->supportedTextureFormat/ { supported=1 }
    /#ifndef Q_OS_ANDROID/ { android_guard=1 }
    android_guard && /meta.uncompressed/ { guarded_uncompressed=1 }
    /if \(!meta.original.isEmpty\(\)\)/ { original=1 }
    END { exit !(compressed && supported && android_guard && guarded_uncompressed && original) }
' "$texture_cache"

generated_qrc="$android_dir/apps/phoneInterface/.cxx/Debug/655u201c/arm64-v8a/android/apps/phoneInterface/libraries/interface/resources.qrc"
if [[ -f "$generated_qrc" ]]; then
    if grep -Eq 'alias="images/Default-Sky-9-cubemap/Default-Sky-9-cubemap(-ambient)?[.]ktx"' "$generated_qrc"; then
        echo 'phone QRC still contains an unreachable uncompressed default-sky KTX' >&2
        exit 1
    fi
    grep -Fq 'Default-Sky-9-cubemap_COMPRESSED_SRGB8_ETC2.ktx' "$generated_qrc"
    grep -Fq 'Default-Sky-9-cubemap_COMPRESSED_RGB_BPTC_UNSIGNED_FLOAT.ktx' "$generated_qrc"
    grep -Fq 'Default-Sky-9-cubemap.texmeta.json' "$generated_qrc"
    if grep -Fq 'alias="meshes/controller/' "$generated_qrc"; then
        echo 'phone QRC still contains VR controller meshes' >&2
        exit 1
    fi
fi

printf 'Phone default-sky payload checks passed.\n'
