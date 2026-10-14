#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../../.." && pwd)"
places="$repo_root/scripts/system/places/places.js"

require() {
    local pattern="$1"
    local description="$2"
    if ! grep -Eq -- "$pattern" "$places"; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
    printf 'PASS: %s\n' "$description"
}

require 'function fetchMetaverse\(index,[[:space:]]*generation\)' \
    'Places UI modes share the non-blocking directory path'
require 'fetchMetaverse\(0,[[:space:]]*generation\)' \
    'Android Phone starts fetching enabled metaverse directories'
require 'request[.]open\("GET",[^;]+,[[:space:]]*true\)' \
    'Android Phone uses asynchronous XMLHttpRequest'
require 'request[.]status[[:space:]]*>=[[:space:]]*200[[:space:]]*&&[[:space:]]*request[.]status[[:space:]]*<[[:space:]]*300' \
    'directory responses require a successful HTTP status'
require 'generation[[:space:]]*!==[[:space:]]*requestGeneration' \
    'late responses from a closed or refreshed Places view are ignored'
require 'fetchMetaverse\(index[[:space:]]*\+[[:space:]]*1,[[:space:]]*generation\)' \
    'a failed directory does not prevent remaining directories from loading'
require 'finishPortalList\(\)' \
    'online and utility entries share one final delivery path'

if grep -Eq '[.]open\("GET",[^;]+,[[:space:]]*false\)' "$places"; then
    printf 'FAIL: Places can enter a synchronous directory request\n' >&2
    exit 1
fi
printf 'PASS: Places does not contain a synchronous directory request\n'

printf 'Phone Places online-directory contract passed.\n'
