#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../.." && pwd)"
readonly settings="$repo_root/scripts/system/settings/Settings.qml"
readonly desktop_config="$repo_root/scripts/system/settings/qml/SettingsTouchConfiguration.qml"
readonly phone_config="$repo_root/scripts/system/settings/qml/+android_phoneInterface/SettingsTouchConfiguration.qml"
readonly pico_config="$repo_root/scripts/system/settings/qml/+android_picoInterface/SettingsTouchConfiguration.qml"
readonly quest_config="$repo_root/scripts/system/settings/qml/+android_questInterface/SettingsTouchConfiguration.qml"
readonly file_utils="$repo_root/libraries/shared/src/shared/FileUtils.cpp"

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
require "$desktop_config" 'showPicoInteractionSettings:[[:space:]]*false' \
    'unselected Settings profiles fail closed for Pico interaction controls'
require "$phone_config" 'showPicoInteractionSettings:[[:space:]]*false' \
    'phone Settings reject the Pico interaction page'
require "$pico_config" 'showPicoInteractionSettings:[[:space:]]*true' \
    'the compiled Pico selector enables Pico interaction controls'
require "$quest_config" 'showPicoInteractionSettings:[[:space:]]*false' \
    'Quest Settings reject Pico-specific interaction controls'
require "$file_utils" 'extraSelectors << "android_" HIFI_ANDROID_APP' \
    'Settings capabilities derive from the immutable compiled Android target'
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
require "$settings" 'requiresPicoInteractionSettings:[[:space:]]*true' \
    'Settings mark Pico-only navigation with an explicit capability'
require "$settings" 'touchConfiguration[.]showPicoInteractionSettings' \
    'Settings filter Pico-only navigation through QFileSelector'
require "$settings" 'active:[[:space:]]*touchConfiguration[.]showPicoInteractionSettings' \
    'non-Pico products do not construct Pico interaction controls'
if grep -Fq 'deferTabletCreationUntilOpen' "$settings"; then
    printf 'FAIL: Settings must not infer immutable product identity from persisted state\n' >&2
    exit 1
fi
printf 'PASS: Settings do not infer product identity from persisted state\n'

readonly graphics="$repo_root/scripts/system/settings/qml/pages/GraphicsSettings.qml"
require "$graphics" 'SettingsTouchConfiguration[[:space:]]*\{[[:space:]]*id:[[:space:]]*touchConfiguration' \
    'Graphics Settings resolves its own lexically scoped phone selector'
require "$graphics" 'visible:[[:space:]]*touchConfiguration[.]showPicoResolutionSettings' \
    'Graphics Settings selector-gates the Pico-only render scale control'

printf 'Phone tablet Settings scale checks passed.\n'
