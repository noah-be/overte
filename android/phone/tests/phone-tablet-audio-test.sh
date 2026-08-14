#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../../.." && pwd)"

audio="$repo_root/interface/resources/qml/hifi/audio/Audio.qml"
shared_config="$repo_root/interface/resources/qml/hifi/audio/AudioTouchConfiguration.qml"
base_profile="$repo_root/interface/resources/qml/controlsUit/TouchUiProfileBase.qml"
phone_profile="$repo_root/interface/resources/qml/controlsUit/+android_phoneInterface/TouchUiProfile.qml"

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
    'Audio resolves presentation through the shared capability configuration'
require "$shared_config" 'showModeTabs:[[:space:]]*profile[.]audioModeTabsAvailable' \
    'Audio derives mode navigation from the device profile'
require "$base_profile" 'property bool audioModeTabsAvailable:[[:space:]]*true' \
    'desktop and VR retain the established audio mode tabs'
require "$base_profile" 'property bool vrAudioAvailable:[[:space:]]*true' \
    'VR clients retain their audio controls'
require "$phone_profile" 'audioModeTabsAvailable:[[:space:]]*false' \
    'phone Audio omits the redundant single Desktop mode tab'
require "$phone_profile" 'vrAudioAvailable:[[:space:]]*false' \
    'phone Audio does not offer unavailable HMD configuration'
require "$phone_profile" 'pushToTalkAvailable:[[:space:]]*false' \
    'phone Audio omits the unavailable desktop keyboard push-to-talk contract'
require "$phone_profile" 'avatarAudioToolsAvailable:[[:space:]]*false' \
    'phone Audio omits the unavailable desktop avatar audio-tools overlay'
require "$shared_config" 'minimumControlHeight:[[:space:]]*directTouch' \
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
