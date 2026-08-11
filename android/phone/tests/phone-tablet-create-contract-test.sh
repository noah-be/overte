#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../../.." && pwd)"
defaults="$repo_root/scripts/+android_phoneInterface/defaultScripts.js"
create="$repo_root/scripts/system/create/edit.js"

if grep -Fq 'system/create/edit.js' "$defaults"; then
    printf 'FAIL: Create is offered before its phone isolation contract is complete\n' >&2
    exit 1
fi
printf 'PASS: incomplete Create is not offered on the Android phone tablet\n'

require_dependency() {
    local pattern="$1"
    local description="$2"
    if ! grep -Eq -- "$pattern" "$create"; then
        printf 'FAIL: Create audit no longer covers %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: Create remains disabled while it depends on %s\n' "$description"
}

# Re-enabling Create requires replacing every one of these interaction classes
# with a touch-owned, screen-space implementation and adding lifecycle tests.
require_dependency 'Desktop[.]createWindow' 'desktop-native windows'
require_dependency 'Controller[.]enableMapping' 'controller mappings'
require_dependency 'Controller[.]captureEntityClickEvents' 'world entity-click capture'
require_dependency 'OverlaySystemWindow|OverlayWebWindow' 'overlay windows'
require_dependency 'Camera[.]mode|cameraManager' 'global camera state'
require_dependency 'Render[.]cameraClippingEnabled' 'global renderer state'

printf 'Android phone Create isolation contract passed.\n'
