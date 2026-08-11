#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
readonly bundled_jdk="$android_root/pico-host-tools/jdk-21"

if [[ -z "${JAVA_HOME:-}" && -x "$bundled_jdk/bin/java" ]]; then
    export JAVA_HOME="$bundled_jdk"
fi
if [[ -n "${JAVA_HOME:-}" ]]; then
    export PATH="$JAVA_HOME/bin:$PATH"
fi

"$android_root/gradlew" --no-daemon -c "$android_root/settings-phone.gradle" \
    :phoneInterface:createDebugUnitTestCoverageReport

exec python3 "$android_root/common/tests/coverage/verify-jvm-coverage.py" \
    "$android_root/phone/apps/phoneInterface/build/reports/coverage/test/debug/report.xml"
