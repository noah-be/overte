#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
readonly bundled_jdk="$android_root/vr/pico/pico-host-tools/jdk-21"

if [[ -z "${JAVA_HOME:-}" && -x "$bundled_jdk/bin/java" ]]; then
    export JAVA_HOME="$bundled_jdk"
fi

exec "$android_root/common/gradlew" --no-daemon -c "$android_root/phone/settings.gradle" \
    :phoneInterface:createDebugAndroidTestCoverageReport
