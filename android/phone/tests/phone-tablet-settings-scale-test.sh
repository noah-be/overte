#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../../.." && pwd)"
readonly settings="$repo_root/scripts/system/settings/Settings.qml"
readonly shared_config="$repo_root/scripts/system/settings/qml/SettingsTouchConfiguration.qml"
readonly base_profile="$repo_root/interface/resources/qml/controlsUit/TouchUiProfileBase.qml"
readonly phone_profile="$repo_root/interface/resources/qml/controlsUit/+android_phoneInterface/TouchUiProfile.qml"

require() {
    local file="$1" pattern="$2" description="$3"
    if ! grep -Eq -- "$pattern" "$file"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

require "$shared_config" 'contentScale:[[:space:]]*1[.]0' \
    'desktop Settings retain their established scale'
require "$shared_config" 'HifiControls[.]TouchUiMetrics' \
    'phone Settings avoid compounding the shared tablet-app scale'
require "$phone_profile" 'controllerSettingsAvailable:[[:space:]]*false' \
    'phone Settings hide the unavailable desktop and VR controller page'
require "$phone_profile" 'graphicsSettingsAvailable:[[:space:]]*false' \
    'phone Settings hide the unbounded desktop graphics page'
require "$phone_profile" 'picoResolutionSettingsAvailable:[[:space:]]*false' \
    'phone Settings hide the Pico-only render scale restart control'
require "$shared_config" 'showGraphicsSettings:[[:space:]]*profile[.]graphicsSettingsAvailable' \
    'Settings resolve policy through the shared device profile'
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
require "$graphics" 'SettingsTouchConfiguration[[:space:]]*\{' \
    'Graphics Settings resolves its own shared capability configuration'
require "$graphics" 'id:[[:space:]]*touchConfiguration' \
    'Graphics Settings keeps its configuration lexically scoped'
require "$graphics" 'visible:[[:space:]]*touchConfiguration[.]showPicoResolutionSettings' \
    'Graphics Settings selector-gates the Pico-only render scale control'

printf 'Phone tablet Settings scale checks passed.\n'
