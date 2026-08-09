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
    OVERTE_JUNIT_TEMP_REPORT="$(mktemp "$junit_report_dir/.${junit_report_name%.xml}.XXXXXX.xml")"
}

overte_junit_publish() {
    if [[ -z "${OVERTE_JUNIT_TEMP_REPORT:-}" || -z "${OVERTE_JUNIT_FINAL_REPORT:-}" ]]; then
        printf 'FAIL: JUnit report publication was not prepared\n' >&2
        return 2
    fi
    if [[ ! -s "$OVERTE_JUNIT_TEMP_REPORT" ]]; then
        return 0
    fi
    if [[ -L "$OVERTE_JUNIT_FINAL_REPORT" ]]; then
        printf 'FAIL: refusing to replace symlinked JUnit report: %s\n' \
            "$OVERTE_JUNIT_FINAL_REPORT" >&2
        return 1
    fi
    mv -f -- "$OVERTE_JUNIT_TEMP_REPORT" "$OVERTE_JUNIT_FINAL_REPORT"
    OVERTE_JUNIT_TEMP_REPORT=""
}

overte_junit_cleanup() {
    if [[ -n "${OVERTE_JUNIT_TEMP_REPORT:-}" ]]; then
        rm -f -- "$OVERTE_JUNIT_TEMP_REPORT"
    fi
}
