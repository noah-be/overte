#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 1 || ! -f $1 ]]; then
    echo "Usage: ./tests/check-phone-apk-16k.sh <apk>" >&2
    exit 2
fi

readonly apk=$1
readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"$script_dir/check-phone-apk-metadata.sh" "$apk"
"$script_dir/check-phone-apk-contents.py" "$apk"
"$script_dir/check-phone-elf-alignment.sh" "$apk"
"$script_dir/check-phone-apk-padding.py" "$apk"

android_sdk=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}
zipalign_bin="$android_sdk/build-tools/36.0.0/zipalign"
if [[ ! -x "$zipalign_bin" ]]; then
    echo "ERROR: Build-Tools 36.0.0 zipalign was not found: $zipalign_bin" >&2
    exit 2
fi

"$zipalign_bin" -c -P 16 -v 4 "$apk"
echo "APK ELF and ZIP entries satisfy the Android 16 KiB packaging gates."
