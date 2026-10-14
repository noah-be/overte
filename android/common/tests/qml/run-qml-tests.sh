#!/usr/bin/env bash
set -euo pipefail

qml_runner="${OVERTE_QML_TEST_RUNNER:-$(command -v qmltestrunner 2>/dev/null || true)}"
if [[ -z "$qml_runner" ]]; then
    for candidate in /usr/lib64/qt5/bin/qmltestrunner /usr/lib/qt5/bin/qmltestrunner; do
        [[ -x "$candidate" ]] && { qml_runner="$candidate"; break; }
    done
fi
if [[ -z "$qml_runner" ]]; then
    printf 'SKIP: qmltestrunner is not installed; QML tests require the project Qt host tools.\n'
    if [[ "${OVERTE_REQUIRE_QML_TESTS:-0}" == 1 ]]; then
        exit 1
    fi
    exit 77
fi

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly android_root="$(cd -- "$script_dir/../../.." && pwd)"
readonly report_dir="${OVERTE_TEST_REPORT_DIR:-$android_root/build/test-results}/qml"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
source "$script_dir/../reporting/atomic-junit-report.sh"
qml_report_succeeded() {
    python3 - "$1" <<'PY'
import sys
import xml.etree.ElementTree as ET
try:
    root = ET.parse(sys.argv[1]).getroot()
    cases = root.findall('testcase')
    valid = (root.tag == 'testsuite' and len(cases) > 0
             and int(root.get('tests', '-1')) == len(cases)
             and all(int(root.get(key, '0')) == 0 for key in ('errors', 'failures', 'skipped'))
             # Qt5 adds result="pass"; Qt6 uses standard JUnit without it.
             and all(case.get('result', 'pass') == 'pass' for case in cases)
             and not any(root.findall('.//' + tag) for tag in ('error', 'failure', 'skipped')))
except (ET.ParseError, OSError, ValueError):
    valid = False
raise SystemExit(0 if valid else 1)
PY
}
overte_junit_prepare "$report_dir" TEST-qml.xml
trap overte_junit_cleanup EXIT
set +e
"$qml_runner" -input "$script_dir" \
    -import "$script_dir" -import "$script_dir/imports" \
    -o -,txt -o "$OVERTE_JUNIT_TEMP_REPORT,junitxml"
status=$?
set -e
if (( status == 77 )); then
    # The tool was found. A selected runtime cannot claim optional tool absence.
    status=1
fi
if ! overte_junit_publish && (( status == 0 )); then
    status=1
fi
if (( status == 0 )) && ! qml_report_succeeded "$OVERTE_JUNIT_FINAL_REPORT"; then
    status=1
fi
overte_junit_cleanup

# The Phone leaf supplies this one fixed runtime contract. Parent-only checkouts
# have neither file. A partial installation or any selected child failure is fatal.
readonly phone_runner="$android_root/phone/tests/phone-places-delegate-test.py"
readonly phone_fixture="$android_root/phone/tests/qml/tst_phone_places_delegates.qml"
readonly phone_domain_fixture="$android_root/phone/tests/qml/tst_phone_login_domain.qml"
if [[ -e "$phone_runner" || -e "$phone_fixture" || -e "$phone_domain_fixture" ]]; then
    if [[ ! -f "$phone_runner" || ! -f "$phone_fixture" || ! -f "$phone_domain_fixture" ]]; then
        echo 'FAIL: incomplete Phone Places runtime contract' >&2
        exit 1
    fi
    overte_junit_prepare "$report_dir" TEST-phone-places.xml
    set +e
    python3 "$phone_runner" --runner "$qml_runner" --junit "$OVERTE_JUNIT_TEMP_REPORT"
    phone_status=$?
    set -e
    if (( phone_status == 77 )); then
        phone_status=1
    fi
    if ! overte_junit_publish; then
        phone_status=1
    fi
    if (( phone_status == 0 )) && ! qml_report_succeeded "$OVERTE_JUNIT_FINAL_REPORT"; then
        phone_status=1
    fi
    if (( status == 0 && phone_status != 0 )); then
        status=$phone_status
    fi
fi
exit "$status"
