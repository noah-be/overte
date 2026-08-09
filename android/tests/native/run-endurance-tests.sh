#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly build_dir="${OVERTE_NATIVE_TEST_BUILD_DIR:-$script_dir/.build}"
readonly cycles="${OVERTE_NATIVE_ENDURANCE_CYCLES:-100}"

if [[ ! "$cycles" =~ ^[0-9]+$ ]] || (( cycles < 1 || cycles > 10000 )); then
    echo "OVERTE_NATIVE_ENDURANCE_CYCLES must be an integer from 1 through 10000" >&2
    exit 2
fi

"$script_dir/run-native-tests.sh" >/dev/null

for (( cycle = 1; cycle <= cycles; ++cycle )); do
    "$build_dir/phone_graphics_deterministic_properties"
    "$build_dir/phone_pending_handoff_deterministic_properties"
done

echo "Native policy endurance passed: $cycles cycles, $((cycles * 1024)) generated parser cases and $((cycles * 4096)) handoff operations"
