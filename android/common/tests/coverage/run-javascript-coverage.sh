#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
readonly report_dir="${OVERTE_JAVASCRIPT_COVERAGE_REPORT_DIR:-$android_root/build/reports/coverage/javascript}"
readonly npm_command="${OVERTE_NPM_COMMAND:-npm}"
readonly summary_file="$report_dir/summary.txt"
readonly lock_file="$report_dir/.summary.txt.lock"
mkdir -p "$report_dir"

lock_timeout="${OVERTE_JAVASCRIPT_COVERAGE_LOCK_TIMEOUT_SECONDS:-600}"
if [[ ! "$lock_timeout" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    printf 'FAIL: invalid JavaScript coverage lock timeout: %s\n' "$lock_timeout" >&2
    exit 2
fi
exec {coverage_lock_fd}>>"$lock_file"
if ! flock -x -w "$lock_timeout" "$coverage_lock_fd"; then
    printf 'FAIL: timed out waiting for JavaScript coverage lock: %s\n' "$lock_file" >&2
    exit 1
fi
staging_file=''
cleanup() {
    [[ -z "$staging_file" ]] || rm -f -- "$staging_file"
    flock -u "$coverage_lock_fd" 2>/dev/null || true
    exec {coverage_lock_fd}>&-
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ -L "$summary_file" ]]; then
    printf 'FAIL: JavaScript coverage summary cannot be a symlink.\n' >&2
    exit 1
fi
rm -f -- "$summary_file"
staging_file="$(mktemp "$report_dir/.summary.txt.XXXXXXXX")"

(
    cd "$android_root/common/tests/javascript"
    "$npm_command" run coverage
) | tee "$staging_file"
mv -f -- "$staging_file" "$summary_file"
staging_file=''
