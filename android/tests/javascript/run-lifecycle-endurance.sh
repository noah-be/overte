#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly javascript_root="$android_root/tests/javascript"
readonly cycles="${OVERTE_JS_ENDURANCE_CYCLES:-20}"

if [[ ! "$cycles" =~ ^[0-9]+$ ]] || (( cycles < 1 || cycles > 500 )); then
    echo "OVERTE_JS_ENDURANCE_CYCLES must be an integer from 1 through 500" >&2
    exit 2
fi
if ! command -v node >/dev/null 2>&1; then
    echo "SKIP: Node.js is required for JavaScript lifecycle endurance" >&2
    exit 77
fi

readonly output="$(mktemp "${TMPDIR:-/tmp}/overte-js-endurance.XXXXXXXX")"
trap 'rm -f -- "$output"' EXIT
readonly lifecycle_pattern='shutdown|tears down valid portals|cancels navigation on unload|removes both buttons'
readonly tests=(
    "$javascript_root/test/mobile-tablet-apps.production.test.js"
    "$javascript_root/test/mobile-action-bar.production.test.js"
    "$javascript_root/test/phone-emote.production.test.js"
    "$javascript_root/test/places.production.test.js"
    "$javascript_root/test/portal.production.test.js"
    "$javascript_root/test/quick-goto.production.test.js"
)

for (( cycle = 1; cycle <= cycles; ++cycle )); do
    if ! node --test --test-name-pattern="$lifecycle_pattern" "${tests[@]}" >"$output" 2>&1; then
        echo "JavaScript lifecycle endurance failed in deterministic cycle $cycle/$cycles" >&2
        sed -n '1,240p' "$output" >&2
        exit 1
    fi
done

echo "JavaScript lifecycle endurance passed: $cycles cycles across ${#tests[@]} production scripts"
