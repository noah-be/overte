#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../../.." && pwd)"
readonly shared_preferences="$repo_root/interface/resources/qml/hifi/tablet/TabletGeneralPreferences.qml"
readonly shared_policy="$repo_root/interface/resources/qml/hifi/tablet/TabletGeneralPreferencesPolicy.qml"
readonly base_profile="$repo_root/interface/resources/qml/controlsUit/TouchUiProfileBase.qml"
readonly phone_profile="$repo_root/interface/resources/qml/controlsUit/+android_phoneInterface/TouchUiProfile.qml"
readonly tablet_preferences_dialog="$repo_root/interface/resources/qml/hifi/tablet/tabletWindows/TabletPreferencesDialog.qml"
readonly preference_source="$repo_root/interface/src/ui/PreferencesDialog.cpp"
readonly phone_gradle="$repo_root/android/phone/apps/phoneInterface/build.gradle"
readonly discord_stub="$repo_root/android/common/cmake/pico-modules/discord_rpc.h"

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

require "$shared_policy" 'profile[.]navigationPreferencesAvailable' \
    'General Settings admit Navigation only through an explicit capability'
require "$shared_policy" 'categories[.]push\("Mouse Sensitivity"\)' \
    'General Settings retain the shared look-sensitivity category'
require "$shared_preferences" 'showCategories:[[:space:]]*preferencesPolicy[.]allowedCategories' \
    'phone General Settings consume the tested fail-closed category policy'
require "$phone_profile" 'navigationPreferencesAvailable:[[:space:]]*true' \
    'phone General Settings expose Navigation'
require "$phone_profile" 'userInterfacePreferencesAvailable:[[:space:]]*false' \
    'phone General Settings exclude incomplete desktop UI controls'
require "$phone_profile" 'hmdPreferencesAvailable:[[:space:]]*false' \
    'phone General Settings exclude HMD controls'
require "$phone_profile" 'snapshotPreferencesAvailable:[[:space:]]*false' \
    'phone General Settings exclude filesystem-backed Snapshot controls'
require "$phone_profile" 'privacyPreferencesAvailable:[[:space:]]*false' \
    'phone General Settings exclude incomplete Privacy controls'
require "$phone_profile" 'pluginPreferencesAvailable:[[:space:]]*false' \
    'phone General Settings exclude unavailable plugin controls'
require "$shared_policy" 'Individual hidden controls' \
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
require "$shared_policy" 'whole category' \
    'shared policy documents why incomplete categories are excluded'
require "$tablet_preferences_dialog" 'objectName:[[:space:]]*"GeneralPreferencesSave"' \
    'General Settings expose a stable semantic identity for Save'
require "$tablet_preferences_dialog" 'Accessible[.]description:[[:space:]]*qsTr\("Save all changed preferences"\)' \
    'General Settings describe the Save action independently of its visual label'
require "$shared_preferences" 'objectName:[[:space:]]*"stack"' \
    'General Settings preserve the native StackView routing identity'
require "$shared_preferences" 'objectName:[[:space:]]*profileRoot[.]semanticScreenId' \
    'General Settings expose the versioned semantic screen identity on the visible dialog'
require "$tablet_preferences_dialog" 'objectName:[[:space:]]*"nav[.]back"' \
    'General Settings expose the contract Back control'
require "$tablet_preferences_dialog" 'Accessible[.]description:[[:space:]]*qsTr\("Discard changed preferences"\)' \
    'General Settings describe the destructive Cancel result'
require "$tablet_preferences_dialog" 'androidClickAction:[[:space:]]*function\(\)[[:space:]]*\{' \
    'General Settings route Android semantic activation through the real button handler'
require "$tablet_preferences_dialog" 'dialog[.]parent[.]sendToScript\(\{[[:space:]]*type:[[:space:]]*"settings[.]back"[[:space:]]*\}\)' \
    'General Settings Back discards edits and returns through the allowlisted Phone router'

require "$base_profile" 'property bool userInterfacePreferencesAvailable:[[:space:]]*true' \
    'desktop General Settings retain User Interface preferences'
require "$base_profile" 'property bool hmdPreferencesAvailable:[[:space:]]*true' \
    'desktop and VR General Settings retain HMD preferences'
require "$base_profile" 'property bool snapshotPreferencesAvailable:[[:space:]]*true' \
    'desktop General Settings retain Snapshot preferences'
require "$base_profile" 'property bool pluginPreferencesAvailable:[[:space:]]*true' \
    'desktop and VR General Settings retain their established categories'

printf 'Android phone General Settings contract checks passed.\n'
