#!/usr/bin/env bash
set -euo pipefail

qml_runner="${OVERTE_QML_TEST_RUNNER:-$(command -v qmltestrunner 2>/dev/null || true)}"
if [[ -z "$qml_runner" && -x /usr/lib/qt5/bin/qmltestrunner ]]; then
    qml_runner=/usr/lib/qt5/bin/qmltestrunner
fi
if [[ -z "$qml_runner" ]]; then
    echo "SKIP: qmltestrunner is required for QML lifecycle endurance"
    if [[ "${OVERTE_REQUIRE_QML_TESTS:-0}" == 1 ]]; then
        exit 1
    fi
    exit 77
fi

readonly qml_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly android_root="$(cd -- "$qml_dir/../.." && pwd)"
readonly report_dir="${OVERTE_TEST_REPORT_DIR:-$android_root/build/test-results}/qml-endurance"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
source "$qml_dir/../reporting/atomic-junit-report.sh"
overte_junit_prepare "$report_dir" TEST-qml-endurance.xml
trap overte_junit_cleanup EXIT
set +e
"$qml_runner" -input "$qml_dir/../qml_endurance" \
    -import "$qml_dir" -import "$qml_dir/imports" \
    -o -,txt -o "$OVERTE_JUNIT_TEMP_REPORT,junitxml"
status=$?
set -e
if ! overte_junit_publish && (( status == 0 )); then
    status=1
fi
exit "$status"
