#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
shield="$repo_root/scripts/system/bubble.js"

require() {
    local pattern="$1"
    local description="$2"
    if ! grep -Eq -- "$pattern" "$shield"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

require 'text:[[:space:]]*buttonName' \
    'Shield registers its tablet action'
require 'function toggleShield\(\)' \
    'Shield uses a lifecycle-aware click handler'
require 'Users[.]toggleIgnoreRadius\(\)' \
    'Shield toggles the established privacy radius'
require 'if[[:space:]]*\(isAndroidPhone\)' \
    'Shield distinguishes Android phone behavior'
require 'tablet[.]hideAndroidTablet\(\)' \
    'Phone Shield closes the tablet after its world action'
require 'if[[:space:]]*\(!isAndroidPhone\)' \
    'Phone Shield avoids mutable tablet-button proxy updates'
require 'if[[:space:]]*\(!isAndroidPhone\)[[:space:]]*\{[[:space:]]*$' \
    'Shield scopes desktop-only setup and teardown away from Phone'
require 'Menu[.]addMenuItem\(\{' \
    'desktop and Pico retain the HUD Shield menu preference'
if awk '
    /Menu[.]addMenuItem/ { if (!guarded) exit 1 }
    /if \(!isAndroidPhone\)/ { guarded = 1 }
' "$shield"; then
    printf 'PASS: Phone does not register the desktop HUD Shield menu preference\n'
else
    printf 'FAIL: Shield menu preference is not guarded from Phone\n' >&2
    exit 1
fi
require 'button[.]clicked[.]disconnect\(toggleShield\)' \
    'Shield disconnects its exact click handler during teardown'
require 'Entities[.]deleteEntity\(bubbleOverlay\)' \
    'Shield removes its local feedback entity during teardown'

printf 'Phone tablet Shield checks passed.\n'
