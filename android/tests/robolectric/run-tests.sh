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

"$gradlew_command" --no-daemon \
    -c "$android_root/tests/robolectric/settings.gradle" \
    -b "$android_root/tests/robolectric/build.gradle" test

python3 - "$report_dir" <<'PY'
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

MAX_COUNTER = 1_000_000_000


def number(value, label):
    if value is None or not re.fullmatch(r"[0-9]+", value):
        raise ValueError(f"invalid {label} counter")
    result = int(value)
    if result > MAX_COUNTER:
        raise ValueError(f"invalid {label} counter")
    return result


def report_tests(path):
    root = ET.parse(path).getroot()
    if root.tag == "testsuite":
        suites = [root]
    elif root.tag == "testsuites":
        suites = list(root.findall("testsuite"))
        if not suites:
            cases = list(root.findall("testcase"))
            if cases:
                return len(cases)
            raise ValueError("testsuites report has no suites or cases")
    else:
        raise ValueError("unsupported JUnit root")
    totals = {
        key: sum(number(suite.get(key), key) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    if totals["failures"] + totals["errors"] + totals["skipped"] > totals["tests"]:
        raise ValueError("inconsistent JUnit counters")
    return totals["tests"]


try:
    reports = sorted(Path(sys.argv[1]).glob("TEST-*.xml"))
    if not reports:
        raise ValueError("no fresh JUnit reports")
    if sum(report_tests(path) for path in reports) <= 0:
        raise ValueError("JUnit reports contain no tests")
except (ET.ParseError, OSError, TypeError, ValueError) as error:
    print(f"error: invalid Robolectric JUnit output: {error}", file=sys.stderr)
    raise SystemExit(1)
PY
