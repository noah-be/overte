#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
places="$repo_root/scripts/system/places/places.js"
qml="$repo_root/scripts/system/places/PicoPlaces.qml"

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

require "$places" 'useQmlApp[[:space:]]*=[[:space:]]*!PlatformInfo[.]has3DHTML\(\)' \
    'Phone Places selects its local QML application'
require "$places" 'qmlEventsConnected[[:space:]]*=[[:space:]]*false' \
    'Places tracks its QML bridge lifecycle'
require "$places" 'if[[:space:]]*\(!qmlEventsConnected\)' \
    'Places prevents duplicate QML bridge connections'
require "$places" 'disconnectQmlEvents\(\);' \
    'Places disconnects its QML bridge when leaving the app'
require "$places" 'disconnectWebEvents\(\);' \
    'Places also releases its desktop web bridge on external navigation'
require "$places" 'if[[:space:]]*\(!isAndroidPhone\)' \
    'Phone Places avoids mutable tablet-button proxy updates'
require "$qml" 'height:[[:space:]]*Math[.]max\(82,' \
    'Places list entries expose touch-sized delegates'
require "$qml" 'ScrollBar[.]vertical:[[:space:]]*ScrollBar' \
    'Places exposes scroll position for long result lists'

printf 'Phone tablet Places checks passed.\n'
