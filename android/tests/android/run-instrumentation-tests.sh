#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly bundled_jdk="$android_root/pico-host-tools/jdk-21"
readonly gradlew_command="${OVERTE_INSTRUMENTATION_GRADLEW_COMMAND:-$android_root/gradlew}"

if [[ "${PHONE_DEVICE_LOCK_HELD:-0}" != 1 ]]; then
    exec "$android_root/phone-device-lock.sh" run -- \
        "$android_root/tests/android/run-instrumentation-tests.sh" "$@"
fi

if [[ -z "${JAVA_HOME:-}" && -x "$bundled_jdk/bin/java" ]]; then
    export JAVA_HOME="$bundled_jdk"
fi
if [[ -n "${JAVA_HOME:-}" ]]; then
    export PATH="$JAVA_HOME/bin:$PATH"
fi

exec "$gradlew_command" --no-daemon -c "$android_root/settings-phone.gradle" \
    :phoneInterface:connectedDebugAndroidTest
