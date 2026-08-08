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
require 'button[.]clicked[.]disconnect\(toggleShield\)' \
    'Shield disconnects its exact click handler during teardown'
require 'Entities[.]deleteEntity\(bubbleOverlay\)' \
    'Shield removes its local feedback entity during teardown'

printf 'Phone tablet Shield checks passed.\n'
