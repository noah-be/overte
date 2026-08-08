#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
avatar="$repo_root/scripts/system/avatarapp.js"
qml="$repo_root/interface/resources/qml/hifi/AvatarApp.qml"
settings_qml="$repo_root/interface/resources/qml/hifi/avatarapp/Settings.qml"
desktop_config="$repo_root/interface/resources/qml/hifi/avatarapp/AvatarTouchConfiguration.qml"
phone_config="$repo_root/interface/resources/qml/hifi/avatarapp/+android_phoneInterface/AvatarTouchConfiguration.qml"

require() {
    local pattern="$1"
    local description="$2"
    if ! grep -Eq -- "$pattern" "$avatar"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

test -s "$qml" || {
    printf 'FAIL: local Avatar QML is missing\n' >&2
    exit 1
}
printf 'PASS: Avatar opens a packaged QML application\n'

require_qml() {
    local file="$1" pattern="$2" description="$3"
    if ! grep -Eq -- "$pattern" "$file"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

require_qml "$desktop_config" 'favoritesFillBelowHeader:[[:space:]]*false' \
    'desktop Avatar retains its established favorites layout'
require_qml "$phone_config" 'favoritesFillBelowHeader:[[:space:]]*true' \
    'phone Avatar places its favorites list below the app header'
require_qml "$qml" 'root[.]height[[:space:]]*-[[:space:]]*header[.]height' \
    'phone favorites consume only the area below the app status header'
require_qml "$phone_config" 'showDominantHand:[[:space:]]*false' \
    'phone Avatar hides tracked-hand preference controls'
require_qml "$phone_config" 'showHmdAlignment:[[:space:]]*false' \
    'phone Avatar hides HMD-only alignment controls'
require_qml "$desktop_config" 'showDominantHand:[[:space:]]*true' \
    'desktop Avatar retains dominant-hand settings'
require_qml "$desktop_config" 'showHmdAlignment:[[:space:]]*true' \
    'desktop Avatar retains HMD alignment settings'
require_qml "$settings_qml" 'visible:[[:space:]]*touchConfiguration[.]showDominantHand' \
    'Avatar Settings selector-gates the complete dominant-hand row'
require_qml "$settings_qml" 'visible:[[:space:]]*touchConfiguration[.]showHmdAlignment' \
    'Avatar Settings selector-gates the complete HMD alignment row'
require_qml "$settings_qml" 'anchors[.]rightMargin:[[:space:]]*touchConfiguration[.]settingsRightMargin' \
    'Avatar Settings positions actions against the phone right edge'
require_qml "$settings_qml" 'anchors[.]bottomMargin:[[:space:]]*touchConfiguration[.]settingsBottomMargin' \
    'Avatar Settings positions Save and Cancel against the phone bottom edge'

require 'if[[:space:]]*\(!currentAvatar[[:space:]]*\|\|' \
    'avatar changes cannot dereference an uninitialized model'
require 'if[[:space:]]*\(isAndroidPhone\)[[:space:]]*\{' \
    'Avatar distinguishes the Android phone presentation'
require 'External avatar marketplace pages are not supported on Android yet' \
    'Phone Avatar reports its unsupported external web path'
require 'tablet[.]gotoWebScreen\(message[.]url,[[:space:]]*MARKETPLACES_INJECT_SCRIPT_URL\)' \
    'desktop and VR retain external marketplace navigation'
require 'if[[:space:]]*\(!isAndroidPhone\)' \
    'Phone Avatar avoids mutable tablet-button proxy updates'
require 'wireEventBridge\(false\);' \
    'Avatar explicitly releases its QML bridge during shutdown'
require 'cancelScheduledCallbacks\(\);' \
    'Avatar cancels delayed bookmark and wearable updates when the app closes'
require 'if[[:space:]]*\(isWired\)' \
    'Avatar suppresses delayed QML delivery after lifecycle teardown'
require 'Bookmark not found' \
    'Avatar reports missing bookmark selections without changing wearables'
require '!message[.]entityID[[:space:]]*\|\|[[:space:]]*!message[.]properties' \
    'Avatar rejects malformed wearable edits'
require 'Array[.]isArray\(bookmark[.]avatarEntites\)' \
    'Avatar tolerates legacy bookmarks without wearable arrays'

printf 'Phone tablet Avatar checks passed.\n'
