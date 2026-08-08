#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"

audio="$repo_root/interface/resources/qml/hifi/audio/Audio.qml"
desktop_config="$repo_root/interface/resources/qml/hifi/audio/AudioTouchConfiguration.qml"
phone_config="$repo_root/interface/resources/qml/hifi/audio/+android_phoneInterface/AudioTouchConfiguration.qml"

require() {
    local file="$1"
    local pattern="$2"
    local description="$3"
    if ! grep -Eq -- "$pattern" "$file"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

require "$audio" 'AudioTouchConfiguration[[:space:]]*\{' \
    'Audio resolves presentation through QFileSelector'
require "$desktop_config" 'showModeTabs:[[:space:]]*true' \
    'desktop and VR retain the established audio mode tabs'
require "$desktop_config" 'showVrMode:[[:space:]]*true' \
    'VR clients retain their audio controls'
require "$phone_config" 'showModeTabs:[[:space:]]*false' \
    'phone Audio removes its redundant mode selector'
require "$phone_config" 'showVrMode:[[:space:]]*false' \
    'phone Audio does not offer unavailable HMD configuration'
require "$audio" 'currentIndex:[[:space:]]*touchConfiguration[.]showVrMode[[:space:]]*&&[[:space:]]*isVR[[:space:]]*[?][[:space:]]*1[[:space:]]*:[[:space:]]*0' \
    'phone Audio remains on the native desktop audio context'
require "$audio" 'anchors[.]top:[[:space:]]*bar[.]visible[[:space:]]*[?][[:space:]]*bar[.]bottom[[:space:]]*:[[:space:]]*parent[.]top' \
    'phone Audio reclaims the hidden mode selector space'

printf 'Phone tablet Audio checks passed.\n'
