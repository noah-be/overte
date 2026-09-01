#!/usr/bin/env bash
set -Eeuo pipefail

readonly MODULE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$MODULE_DIR/../lib/device-test.sh"

require_installed_phone
adb_for shell am force-stop "$DEVICE_TEST_PACKAGE" >/dev/null
start_phone || fail "launcher activity could not be started"
pid="$(wait_for_phone_pid 30)" || fail "application process did not start"
sleep "${DEVICE_TEST_LAUNCH_SETTLE_SECONDS:-10}"
assert_same_pid "$pid" "launch smoke"
activity_is_resumed || fail "PhoneInterfaceActivity is not resumed"
printf 'pid=%s\nactivity_resumed=1\n' "$pid" >"$DEVICE_TEST_ARTIFACT_DIR/metrics.env"
printf 'Phone launch remained stable.\n'
