#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../.." && pwd)"
readonly phone_preferences="$repo_root/interface/resources/qml/hifi/tablet/+android_phoneInterface/TabletGeneralPreferences.qml"
readonly phone_policy="$repo_root/interface/resources/qml/hifi/tablet/+android_phoneInterface/PhoneGeneralPreferencesPolicy.qml"
readonly shared_preferences="$repo_root/interface/resources/qml/hifi/tablet/TabletGeneralPreferences.qml"
readonly tablet_preferences_dialog="$repo_root/interface/resources/qml/hifi/tablet/tabletWindows/TabletPreferencesDialog.qml"
readonly preference_source="$repo_root/interface/src/ui/PreferencesDialog.cpp"
readonly phone_gradle="$repo_root/android/apps/phoneInterface/build.gradle"
readonly discord_stub="$repo_root/android/cmake-pico-modules/discord_rpc.h"

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

require "$phone_policy" \
    'allowedCategories:[[:space:]]*\["Navigation",[[:space:]]*"Mouse Sensitivity"\]' \
    'phone General Settings use an explicit reviewed category allowlist'
require "$phone_preferences" 'showCategories:[[:space:]]*phonePolicy[.]allowedCategories' \
    'phone General Settings consume the tested fail-closed category policy'
reject "$phone_preferences" \
    'showCategories:.*"(User Interface|HMD|Snapshots|Privacy|Plugins)"' \
    'phone General Settings exclude incomplete, desktop, VR, filesystem, and Oculus categories'
require "$phone_policy" 'Individual hidden controls' \
    'phone filtering documents why whole unsupported categories are excluded'

require "$preference_source" '#if defined\(ANDROID_APP_PHONE_INTERFACE\)' \
    'phone Navigation preferences remain compile-time scoped to phoneInterface'
require "$preference_source" '"android/phone/pinchZoomEnabled"' \
    'phone Navigation retains the touch-specific pinch setting'
require "$preference_source" 'static const QString AVATAR_CAMERA\{ "Mouse Sensitivity" \}' \
    'touch look sensitivity retains its shared runtime category'
require "$phone_gradle" 'USE_BREAKPAD=OFF' \
    'phone build keeps crash reporting disabled'
require "$discord_stub" 'static inline void Discord_UpdatePresence' \
    'phone build resolves Discord presence to its Android no-op stub'
require "$phone_preferences" 'Privacy includes crash reporting and Discord controls' \
    'phone selector documents why the incomplete Privacy category is excluded'
require "$tablet_preferences_dialog" 'objectName:[[:space:]]*"GeneralPreferencesSave"' \
    'General Settings expose a stable semantic identity for Save'
require "$tablet_preferences_dialog" 'Accessible[.]description:[[:space:]]*qsTr\("Save all changed preferences"\)' \
    'General Settings describe the Save action independently of its visual label'
require "$tablet_preferences_dialog" 'objectName:[[:space:]]*"GeneralPreferencesCancel"' \
    'General Settings expose a stable semantic identity for Cancel'
require "$tablet_preferences_dialog" 'Accessible[.]description:[[:space:]]*qsTr\("Discard changed preferences"\)' \
    'General Settings describe the destructive Cancel result'

require "$shared_preferences" \
    'showCategories:.*"User Interface".*"HMD".*"Snapshots".*"Plugins"' \
    'desktop and VR General Settings retain their established categories'

printf 'Android phone General Settings contract checks passed.\n'
