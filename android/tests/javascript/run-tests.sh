#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly android_root="$(cd -- "$script_dir/../.." && pwd)"
readonly report_dir="${OVERTE_TEST_REPORT_DIR:-$android_root/build/test-results}/javascript"
readonly node_command="${OVERTE_NODE_COMMAND:-node}"
source "$script_dir/../reporting/atomic-junit-report.sh"
overte_junit_prepare "$report_dir" TEST-javascript.xml
trap overte_junit_cleanup EXIT
set +e
"$node_command" --test \
    --test-reporter=spec --test-reporter-destination=stdout \
    --test-reporter=junit --test-reporter-destination="$OVERTE_JUNIT_TEMP_REPORT" \
    "$script_dir"/test/*.test.js
status=$?
set -e
if ! overte_junit_publish && (( status == 0 )); then
    status=1
fi
exit "$status"
