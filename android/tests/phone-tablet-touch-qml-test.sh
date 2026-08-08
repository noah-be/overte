#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"

home="$repo_root/interface/resources/qml/hifi/tablet/TabletHome.qml"
button="$repo_root/interface/resources/qml/hifi/tablet/TabletButton.qml"
shared_config="$repo_root/interface/resources/qml/hifi/tablet/TabletTouchConfiguration.qml"
phone_config="$repo_root/interface/resources/qml/hifi/tablet/+android_phoneInterface/TabletTouchConfiguration.qml"

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

require "$shared_config" 'property bool touchOptimized:[[:space:]]*false' \
    'desktop and VR retain their existing pointer presentation'
require "$phone_config" 'property bool touchOptimized:[[:space:]]*true' \
    'the phone selector enables touchscreen presentation'
require "$phone_config" 'availableWidth[[:space:]]*>=[[:space:]]*availableHeight[[:space:]]*\?[[:space:]]*6[[:space:]]*:[[:space:]]*3' \
    'the phone tablet responds to landscape and transient portrait sizes'
require "$phone_config" 'property int minimumTouchTarget:[[:space:]]*48' \
    'page controls expose touch-sized targets'
require "$home" 'TabletTouchConfiguration[[:space:]]*\{' \
    'TabletHome consumes the selector-backed presentation settings'
require "$home" 'cellWidth:[[:space:]]*width[[:space:]]*/[[:space:]]*presentation\.columns' \
    'the app grid uses the responsive column count'
require "$home" 'width:[[:space:]]*gridView\.buttonExtent' \
    'app buttons scale inside the available landscape grid'
require "$home" 'hoverEnabled:[[:space:]]*!presentation\.touchOptimized' \
    'touch presentation does not depend on hover input'
require "$button" 'hoverEnabled:[[:space:]]*tabletButton\.hoverEnabled' \
    'tablet buttons suppress synthetic hover handling on direct touch'

printf 'Phone tablet touchscreen QML checks passed.\n'
