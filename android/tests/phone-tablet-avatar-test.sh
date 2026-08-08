#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
avatar="$repo_root/scripts/system/avatarapp.js"
qml="$repo_root/interface/resources/qml/hifi/AvatarApp.qml"

require() {
    local pattern="$1"
    local description="$2"
    if ! grep -Eq -- "$pattern" "$avatar"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

test -s "$qml" || {
    printf 'FAIL: local Avatar QML is missing\n' >&2
    exit 1
}
printf 'PASS: Avatar opens a packaged QML application\n'

require 'if[[:space:]]*\(!currentAvatar[[:space:]]*\|\|' \
    'avatar changes cannot dereference an uninitialized model'
require 'if[[:space:]]*\(isAndroidPhone\)[[:space:]]*\{' \
    'Avatar distinguishes the Android phone presentation'
require 'External avatar marketplace pages are not supported on Android yet' \
    'Phone Avatar reports its unsupported external web path'
require 'tablet[.]gotoWebScreen\(message[.]url,[[:space:]]*MARKETPLACES_INJECT_SCRIPT_URL\)' \
    'desktop and VR retain external marketplace navigation'
require 'if[[:space:]]*\(!isAndroidPhone\)' \
    'Phone Avatar avoids mutable tablet-button proxy updates'
require 'wireEventBridge\(false\);' \
    'Avatar explicitly releases its QML bridge during shutdown'

printf 'Phone tablet Avatar checks passed.\n'
