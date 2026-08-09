#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

app_path="${1:-}"
expected_bundle_id="${2:-org.overte.interface.dev}"
[[ -d "$app_path" && "$app_path" == *.app ]] || {
    printf 'usage: %s APP_PATH [BUNDLE_ID]\n' "$0" >&2
    exit 2
}

plist="$app_path/Info.plist"
privacy="$app_path/PrivacyInfo.xcprivacy"
[[ -f "$plist" ]] || { echo "missing Info.plist" >&2; exit 1; }
[[ -f "$privacy" ]] || { echo "missing PrivacyInfo.xcprivacy" >&2; exit 1; }

bundle_id="$(plutil -extract CFBundleIdentifier raw -o - "$plist")"
[[ "$bundle_id" == "$expected_bundle_id" ]] || {
    echo "unexpected bundle identifier: $bundle_id" >&2
    exit 1
}

executable_name="$(plutil -extract CFBundleExecutable raw -o - "$plist")"
executable="$app_path/$executable_name"
[[ -x "$executable" ]] || { echo "missing app executable: $executable" >&2; exit 1; }
lipo -verify_arch arm64 "$executable"

target_family="$(plutil -extract UIDeviceFamily json -o - "$plist")"
[[ "$target_family" == *1* && "$target_family" == *2* ]] || {
    echo "bundle does not target both iPhone and iPad: $target_family" >&2
    exit 1
}

if find "$app_path" -type f \( -name '*.so' -o -name '*.dll' \) -print -quit | grep -q .; then
    echo "bundle contains a forbidden desktop shared library" >&2
    exit 1
fi

if otool -L "$executable" | grep -Eiq 'OpenGL|QtWebEngine|steam|openvr|openxr|discord'; then
    echo "bundle links a forbidden first-port dependency" >&2
    exit 1
fi

echo "Verified iOS app bundle: $app_path"
