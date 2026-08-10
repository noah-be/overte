#!/usr/bin/env bash

# Shared same-filesystem JUnit publication for shell test runners.

overte_junit_prepare() {
    if (( $# != 2 )); then
        printf 'FAIL: overte_junit_prepare requires REPORT_DIR and REPORT_NAME\n' >&2
        return 2
    fi
    local junit_report_dir="$1"
    local junit_report_name="$2"
    if [[ "$junit_report_name" == */* || "$junit_report_name" != TEST-*.xml ]]; then
        printf 'FAIL: invalid JUnit report name: %s\n' "$junit_report_name" >&2
        return 2
    fi
    mkdir -p -- "$junit_report_dir"
    OVERTE_JUNIT_FINAL_REPORT="$junit_report_dir/$junit_report_name"
    OVERTE_JUNIT_LOCK_FILE="$junit_report_dir/.${junit_report_name}.lock"
    local lock_timeout="${OVERTE_JUNIT_LOCK_TIMEOUT_SECONDS:-600}"
    if [[ ! "$lock_timeout" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
        printf 'FAIL: invalid JUnit report lock timeout: %s\n' "$lock_timeout" >&2
        return 2
    fi
    exec {OVERTE_JUNIT_LOCK_FD}>>"$OVERTE_JUNIT_LOCK_FILE"
    if ! flock -x -w "$lock_timeout" "$OVERTE_JUNIT_LOCK_FD"; then
        printf 'FAIL: timed out waiting for JUnit report lock: %s\n' \
            "$OVERTE_JUNIT_LOCK_FILE" >&2
        exec {OVERTE_JUNIT_LOCK_FD}>&-
        return 1
    fi
    if [[ -L "$OVERTE_JUNIT_FINAL_REPORT" ]]; then
        printf 'FAIL: refusing to replace symlinked JUnit report: %s\n' \
            "$OVERTE_JUNIT_FINAL_REPORT" >&2
        flock -u "$OVERTE_JUNIT_LOCK_FD"
        exec {OVERTE_JUNIT_LOCK_FD}>&-
        return 1
    fi
    rm -f -- "$OVERTE_JUNIT_FINAL_REPORT"
    if ! OVERTE_JUNIT_TEMP_REPORT="$(
            mktemp "$junit_report_dir/.${junit_report_name%.xml}.XXXXXX.xml")"; then
        flock -u "$OVERTE_JUNIT_LOCK_FD"
        exec {OVERTE_JUNIT_LOCK_FD}>&-
        return 1
    fi
}

overte_junit_publish() {
    if [[ -z "${OVERTE_JUNIT_TEMP_REPORT:-}" || -z "${OVERTE_JUNIT_FINAL_REPORT:-}" ]]; then
        printf 'FAIL: JUnit report publication was not prepared\n' >&2
        return 2
    fi
    if [[ ! -s "$OVERTE_JUNIT_TEMP_REPORT" ]]; then
        printf 'FAIL: JUnit reporter produced no report\n' >&2
        return 1
    fi
    if ! python3 - "$OVERTE_JUNIT_TEMP_REPORT" <<'PY'
import sys
import xml.etree.ElementTree as ET

try:
    root = ET.parse(sys.argv[1]).getroot()
    if root.tag == "testsuite":
        tests = int(root.get("tests", "0"))
    elif root.tag == "testsuites":
        suites = root.findall("testsuite")
        tests = (sum(int(suite.get("tests", "0")) for suite in suites)
                 if suites else len(root.findall("testcase")))
    else:
        raise ValueError("invalid JUnit root")
    if tests <= 0:
        raise ValueError("JUnit report contains no tests")
except (ET.ParseError, OSError, TypeError, ValueError):
    raise SystemExit(1)
PY
    then
        printf 'FAIL: JUnit reporter produced an invalid report\n' >&2
        return 1
    fi
    mv -f -- "$OVERTE_JUNIT_TEMP_REPORT" "$OVERTE_JUNIT_FINAL_REPORT"
    OVERTE_JUNIT_TEMP_REPORT=""
}

overte_junit_cleanup() {
    if [[ -n "${OVERTE_JUNIT_TEMP_REPORT:-}" ]]; then
        rm -f -- "$OVERTE_JUNIT_TEMP_REPORT"
    fi
    if [[ -n "${OVERTE_JUNIT_LOCK_FD:-}" ]]; then
        flock -u "$OVERTE_JUNIT_LOCK_FD" 2>/dev/null || true
        exec {OVERTE_JUNIT_LOCK_FD}>&-
    fi
}
