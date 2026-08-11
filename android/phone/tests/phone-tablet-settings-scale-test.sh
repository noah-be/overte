#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../../.." && pwd)"
readonly settings="$repo_root/scripts/system/settings/Settings.qml"
readonly desktop_config="$repo_root/scripts/system/settings/qml/SettingsTouchConfiguration.qml"
readonly phone_config="$repo_root/scripts/system/settings/qml/+android_phoneInterface/SettingsTouchConfiguration.qml"

require() {
    local file="$1" pattern="$2" description="$3"
    if ! grep -Eq -- "$pattern" "$file"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

require "$desktop_config" 'contentScale:[[:space:]]*1[.]0' \
    'desktop Settings retain their established scale'
require "$phone_config" 'contentScale:[[:space:]]*1[.]0' \
    'phone Settings avoid compounding the shared tablet-app scale'
require "$phone_config" 'showControllerSettings:[[:space:]]*false' \
    'phone Settings hide the unavailable desktop and VR controller page'
require "$phone_config" 'showGraphicsSettings:[[:space:]]*false' \
    'phone Settings hide the unbounded desktop graphics page'
require "$phone_config" 'showPicoResolutionSettings:[[:space:]]*false' \
    'phone Settings hide the Pico-only render scale restart control'
require "$settings" 'SettingsTouchConfiguration[[:space:]]*\{' \
    'Settings resolve metrics through QFileSelector'
require "$settings" 'width:[[:space:]]*parent[.]width / touchConfiguration[.]contentScale' \
    'logical width compensates for visual scaling without clipping'
require "$settings" 'height:[[:space:]]*parent[.]height / touchConfiguration[.]contentScale' \
    'logical height compensates for visual scaling without clipping'
require "$settings" 'transformOrigin:[[:space:]]*Item[.]TopLeft' \
    'touch scaling stays aligned with the screen origin'
require "$settings" 'scale:[[:space:]]*touchConfiguration[.]contentScale' \
    'the complete Settings surface and its hit targets scale together'
require "$settings" 'requiresControllerSettings:[[:space:]]*true' \
    'Settings mark controller-dependent navigation explicitly'
require "$settings" 'touchConfiguration[.]showControllerSettings' \
    'Settings filter controller-dependent navigation through the selector'
require "$settings" 'requiresGraphicsSettings:[[:space:]]*true' \
    'Settings mark the unbounded graphics page explicitly'
require "$settings" 'touchConfiguration[.]showGraphicsSettings' \
    'Settings filter graphics navigation through the selector'
require "$settings" 'active:[[:space:]]*touchConfiguration[.]showGraphicsSettings' \
    'Phone does not construct hidden desktop graphics controls'

readonly graphics="$repo_root/scripts/system/settings/qml/pages/GraphicsSettings.qml"
require "$graphics" 'SettingsTouchConfiguration[[:space:]]*\{[[:space:]]*id:[[:space:]]*touchConfiguration' \
    'Graphics Settings resolves its own lexically scoped phone selector'
require "$graphics" 'visible:[[:space:]]*touchConfiguration[.]showPicoResolutionSettings' \
    'Graphics Settings selector-gates the Pico-only render scale control'

printf 'Phone tablet Settings scale checks passed.\n'
