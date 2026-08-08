#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../.." && pwd)"
readonly phone_preferences="$repo_root/interface/resources/qml/hifi/tablet/+android_phoneInterface/TabletGeneralPreferences.qml"
readonly shared_preferences="$repo_root/interface/resources/qml/hifi/tablet/TabletGeneralPreferences.qml"
readonly preference_source="$repo_root/interface/src/ui/PreferencesDialog.cpp"

require() {
    local file="$1" pattern="$2" description="$3"
    if ! grep -Eq -- "$pattern" "$file"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

reject() {
    local file="$1" pattern="$2" description="$3"
    if grep -Eq -- "$pattern" "$file"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

require "$phone_preferences" \
    'showCategories:[[:space:]]*\["Navigation",[[:space:]]*"Mouse Sensitivity",[[:space:]]*"Privacy"\]' \
    'phone General Settings use an explicit reviewed category allowlist'
reject "$phone_preferences" \
    'showCategories:.*"(User Interface|HMD|Snapshots|Plugins)"' \
    'phone General Settings exclude desktop, VR, filesystem, and Oculus categories'
require "$phone_preferences" 'Hidden individual preferences are still loaded and saved' \
    'phone filtering documents why whole unsupported categories are excluded'

require "$preference_source" '#if defined\(ANDROID_APP_PHONE_INTERFACE\)' \
    'phone Navigation preferences remain compile-time scoped to phoneInterface'
require "$preference_source" '"android/phone/pinchZoomEnabled"' \
    'phone Navigation retains the touch-specific pinch setting'
require "$preference_source" 'static const QString AVATAR_CAMERA\{ "Mouse Sensitivity" \}' \
    'touch look sensitivity retains its shared runtime category'

require "$shared_preferences" \
    'showCategories:.*"User Interface".*"HMD".*"Snapshots".*"Plugins"' \
    'desktop and VR General Settings retain their established categories'

printf 'Android phone General Settings contract checks passed.\n'
