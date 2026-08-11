#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../../.." && pwd)"

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
    'phone Audio omits the redundant single Desktop mode tab'
require "$phone_config" 'showVrMode:[[:space:]]*false' \
    'phone Audio does not offer unavailable HMD configuration'
require "$phone_config" 'showPushToTalk:[[:space:]]*false' \
    'phone Audio omits the unavailable desktop keyboard push-to-talk contract'
require "$phone_config" 'showAvatarAudioTools:[[:space:]]*false' \
    'phone Audio omits the unavailable desktop avatar audio-tools overlay'
require "$phone_config" 'minimumControlHeight:[[:space:]]*20' \
    'phone Audio exposes physically touchable switches after host scaling'
require "$audio" 'currentIndex:[[:space:]]*touchConfiguration[.]showVrMode[[:space:]]*&&[[:space:]]*isVR[[:space:]]*[?][[:space:]]*1[[:space:]]*:[[:space:]]*0' \
    'phone Audio remains on the native desktop audio context'
require "$audio" 'anchors[.]top:[[:space:]]*bar[.]visible[[:space:]]*[?][[:space:]]*bar[.]bottom[[:space:]]*:[[:space:]]*parent[.]top' \
    'phone Audio reclaims the hidden mode selector space'
require "$audio" 'if[[:space:]]*\(touchConfiguration[.]showPushToTalk\)' \
    'hidden push-to-talk state cannot be written during Phone construction'
require "$audio" 'if[[:space:]]*\(touchConfiguration[.]showAvatarAudioTools\)' \
    'hidden avatar audio-tools state cannot be written during Phone construction'
require "$audio" 'peakValuesEnabledChanged[.]connect\(onPeakValuesEnabledChanged\)' \
    'Audio uses a named peak-level listener'
require "$audio" 'peakValuesEnabledChanged[.]disconnect\(onPeakValuesEnabledChanged\)' \
    'Audio releases its peak-level listener when the tablet app closes'
require "$audio" 'Component[.]onDestruction' \
    'Audio tears down transient metering state during app lifecycle changes'
require "$audio" 'peakValuesEnabled[[:space:]]*=[[:space:]]*root[.]peakValuesWereEnabled' \
    'Audio restores the pre-existing peak-meter state on close'

printf 'Phone tablet Audio checks passed.\n'
