#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"$script_dir/pico-device-lock-test.sh"
"$script_dir/pico-unattended-test-test.sh"
"$script_dir/pico-microphone-test-test.sh"

set +e
prepared_output="$(PICO_HOST_KEEP_LOGS=unexpected \
    "$script_dir/pico-host-regression-test.sh" --build-dir /nonexistent 2>&1)"
prepared_code=$?
set -e
if [[ "$prepared_code" != 2 ||
      "$prepared_output" != *'PICO_HOST_KEEP_LOGS must be 0 or 1'* ]]; then
    printf 'FAIL prepared_host_rejects_invalid_cleanup_policy (exit=%s output=%q)\n' \
        "$prepared_code" "$prepared_output" >&2
    exit 1
fi
printf 'PASS prepared_host_rejects_invalid_cleanup_policy\n'
