#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly bundled_jdk="$android_root/pico-host-tools/jdk-21"
readonly report_dir="${OVERTE_ROBOLECTRIC_REPORT_DIR:-$android_root/tests/robolectric/build/test-results/test}"
readonly lock_file="${OVERTE_ROBOLECTRIC_LOCK_FILE:-$android_root/build/locks/robolectric.lock}"
readonly gradlew_command="${OVERTE_GRADLEW_COMMAND:-$android_root/gradlew}"
lock_timeout="${OVERTE_ROBOLECTRIC_LOCK_TIMEOUT_SECONDS:-900}"
if [[ ! "$lock_timeout" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    printf 'error: invalid Robolectric build lock timeout: %s\n' "$lock_timeout" >&2
    exit 2
fi
mkdir -p -- "$(dirname -- "$lock_file")" "$report_dir"
exec 9>>"$lock_file"
if ! flock -w "$lock_timeout" 9; then
    echo "error: timed out waiting for the repository Robolectric build lock" >&2
    exit 2
fi
rm -f -- "$report_dir"/TEST-*.xml

# The repository-local host toolchain is preferred when present. This also
# prevents a newer workstation JDK from making the pinned Gradle version fail
# before tests start; clean CI uses setup-java 21.
if [[ -n "${OVERTE_ROBOLECTRIC_JAVA_HOME:-}" ]]; then
    export JAVA_HOME="$OVERTE_ROBOLECTRIC_JAVA_HOME"
elif [[ -x "$bundled_jdk/bin/java" ]]; then
    export JAVA_HOME="$bundled_jdk"
fi

readonly java_command="${JAVA_HOME:+$JAVA_HOME/bin/}java"
if ! command -v "$java_command" >/dev/null 2>&1; then
    printf 'error: Java 21 is required for the Robolectric harness.\n' >&2
    exit 2
fi
readonly java_major="$("$java_command" -version 2>&1 |
    sed -n 's/.*version "\([0-9][0-9]*\).*/\1/p' | head -n 1)"
if [[ "$java_major" != 21 ]]; then
    printf 'error: Java 21 is required for reproducible Robolectric tests; found Java %s.\n' \
        "${java_major:-unknown}" >&2
    exit 2
fi

exec "$gradlew_command" --no-daemon \
    -c "$android_root/tests/robolectric/settings.gradle" \
    -b "$android_root/tests/robolectric/build.gradle" test
