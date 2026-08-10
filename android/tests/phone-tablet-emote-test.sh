#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../.." && pwd)"
readonly defaults="$repo_root/scripts/+android_phoneInterface/defaultScripts.js"
readonly script="$repo_root/scripts/system/+android_phoneInterface/phoneEmote.js"
readonly qml="$repo_root/scripts/system/+android_phoneInterface/PhoneEmote.qml"

require() {
    local file="$1" pattern="$2" description="$3"
    if ! grep -Eq -- "$pattern" "$file"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

require "$defaults" 'system/\+android_phoneInterface/phoneEmote[.]js' \
    'phone startup enables the native Emote app'
require "$script" 'tablet[.]loadQMLSource\(APP_SOURCE\)' \
    'phone Emote opens local QML instead of a Web surface'
require "$script" 'appOpen = type === "QML" && source === APP_SOURCE' \
    'Emote accepts QML messages only while its exact surface is open'
require "$script" 'EMOTES[.]indexOf\(name\) === -1' \
    'Emote rejects names outside its local animation allowlist'
require "$script" 'selected[.]resource[.]state !== RESOURCE_FINISHED' \
    'Emote fails safely while an animation resource is unavailable'
require "$script" 'frames[.]length <= 0' \
    'Emote rejects invalid animation frame data'
require "$script" 'Script[.]clearTimeout\(activeTimer\)' \
    'Emote cancels an existing completion timer before replacement'
require "$script" 'MyAvatar[.]restoreAnimation\(\)' \
    'Emote restores avatar animation on stop and teardown'
require "$script" 'if \(wasOpen && !appOpen\)' \
    'leaving the Emote surface restores avatar animation immediately'
require "$script" 'tablet[.]fromQml[.]disconnect\(fromQml\)' \
    'Emote releases its QML message bridge at shutdown'
require "$qml" 'signal sendToScript\(var message\)' \
    'Emote uses the native Tablet QML bridge'
require "$qml" 'cellWidth:[[:space:]]*width / 2' \
    'Emote presents a compact two-column touch grid'
require "$qml" 'cellHeight:[[:space:]]*54' \
    'Emote buttons exceed the phone logical touch minimum'
require "$qml" 'method:[[:space:]]*"phoneEmote[.]play"' \
    'Emote QML emits only its namespaced play request'

if grep -Eq 'gotoWebScreen|webEventReceived|Controller[.]newMapping|editProperties' "$script"; then
    printf 'FAIL: phone Emote retains Web, controller, or mutable-button dependencies\n' >&2
    exit 1
fi
printf 'PASS: phone Emote has no Web, controller, or mutable-button dependency\n'

node --check "$script"
node "$script_dir/phone-tablet-emote-lifecycle-mock.js"
printf 'Android phone Emote contract checks passed.\n'
