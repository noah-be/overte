#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../.." && pwd)"
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
require "$phone_config" 'contentScale:[[:space:]]*1[.]5' \
    'phone Settings use touch-sized content and hit targets'
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

printf 'Phone tablet Settings scale checks passed.\n'
