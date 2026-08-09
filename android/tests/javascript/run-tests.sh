#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly android_root="$(cd -- "$script_dir/../.." && pwd)"
readonly report_dir="${OVERTE_TEST_REPORT_DIR:-$android_root/build/test-results}/javascript"
readonly node_command="${OVERTE_NODE_COMMAND:-node}"
mkdir -p "$report_dir"
temporary_report="$(mktemp "$report_dir/.TEST-javascript.XXXXXX.xml")"
trap 'rm -f -- "$temporary_report"' EXIT
set +e
"$node_command" --test \
    --test-reporter=spec --test-reporter-destination=stdout \
    --test-reporter=junit --test-reporter-destination="$temporary_report" \
    "$script_dir"/test/*.test.js
status=$?
set -e
if [[ -s "$temporary_report" ]]; then
    mv -f -- "$temporary_report" "$report_dir/TEST-javascript.xml"
fi
exit "$status"
