#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly report_dir="$android_root/build/reports/coverage/javascript"
mkdir -p "$report_dir"

(
    cd "$android_root/tests/javascript"
    npm run coverage
) | tee "$report_dir/summary.txt"
