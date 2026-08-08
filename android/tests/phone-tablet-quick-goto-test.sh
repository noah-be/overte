#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
quick_goto="$repo_root/scripts/system/quickGoto.js"
tutorial="$repo_root/interface/resources/serverless/tutorial.json"

require() {
    local pattern="$1"
    local description="$2"
    if ! grep -Eq -- "$pattern" "$quick_goto"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

test -s "$tutorial" || {
    printf 'FAIL: bundled Tutorial destination is missing\n' >&2
    exit 1
}
printf 'PASS: Tutorial opens a bundled serverless destination\n'

require 'typeof tablet[.]hideAndroidTablet === "function"' \
    'world navigation closes the Android screen-space tablet'
require 'LocationBookmarks[.]getHomeLocationAddress\(\)' \
    'Home resolves the user-configured home location'
require 'location[.]handleLookupString\(home\)' \
    'Home uses the established address lookup path'
require 'FALLBACK_DESTINATION = "file:///~/serverless/tutorial[.]json"' \
    'missing Home configuration falls back to bundled content'
require 'typeof candidate !== "string"' \
    'Home rejects non-string persisted bookmark data'
require 'candidate[[:space:]]*=[[:space:]]*candidate[.]trim\(\)' \
    'Home normalizes surrounding bookmark whitespace'
require 'MAX_HOME_DESTINATION_LENGTH = 4096' \
    'Home establishes a bounded script/C++ address contract'
require 'candidate[.]length > MAX_HOME_DESTINATION_LENGTH' \
    'Home rejects overlong persisted bookmark data'
require '\\u0000-\\u001f\\u007f' \
    'Home rejects bookmark values containing control characters'

if grep -Fq 'pico-debug.json' "$quick_goto"; then
    printf 'FAIL: Home still routes users to a development world\n' >&2
    exit 1
fi
printf 'PASS: Home does not expose a development-only destination\n'

node "$script_dir/phone-tablet-quick-goto-mock.js"

printf 'Phone tablet quick navigation checks passed.\n'
