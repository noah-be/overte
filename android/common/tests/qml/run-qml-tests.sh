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
overte_junit_prepare "$report_dir" TEST-qml.xml
trap overte_junit_cleanup EXIT
set +e
"$qml_runner" -input "$script_dir" \
    -import "$script_dir" -import "$script_dir/imports" \
    -o -,txt -o "$OVERTE_JUNIT_TEMP_REPORT,junitxml"
status=$?
set -e
if ! overte_junit_publish && (( status == 0 )); then
    status=1
fi
exit "$status"
