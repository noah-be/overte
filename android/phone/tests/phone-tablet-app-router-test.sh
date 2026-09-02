#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../../.." && pwd)"
readonly router="$repo_root/scripts/system/+android_phoneInterface/mobileTabletApps.js"

require() {
    local pattern="$1" description="$2"
    if ! grep -Eq -- "$pattern" "$router"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

require 'var SETTINGS_ROUTES = \{' \
    'Phone Settings navigation uses an explicit route allowlist'
require 'Object[.]prototype[.]hasOwnProperty[.]call\(SETTINGS_ROUTES,[[:space:]]*message[.]appUrl\)' \
    'route lookup rejects inherited and unknown properties'
require 'typeof message[.]appUrl !== "string"' \
    'route lookup rejects non-string QML payloads'
require 'currentSource !== SETTINGS_SOURCE' \
    'route messages are accepted only from the active Settings surface'
require 'tablet[.]loadQMLSource\(SETTINGS_ROUTES\[message[.]appUrl\]\)' \
    'only an allowlisted resolved route reaches the tablet loader'
require 'semanticId:[[:space:]]*"app[.]settings"' \
    'the actual Phone Settings launcher exposes the common semantic ID'
require 'Object[.]prototype[.]hasOwnProperty[.]call\(SETTINGS_CHILD_SOURCES,[[:space:]]*currentSource\)' \
    'semantic Back accepts only an allowlisted Settings child surface'
require 'message[.]type === "settings[.]back"' \
    'nested visible Back controls use the bounded Phone routing message'
require 'tablet[.]loadQMLSource\(SETTINGS_SOURCE\)' \
    'semantic Back returns through the real Settings loader'

node --check "$router"
node "$script_dir/phone-tablet-app-router-mock.js"
printf 'Android phone tablet app-router checks passed.\n'
