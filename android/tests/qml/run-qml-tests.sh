#!/usr/bin/env bash
set -euo pipefail

qml_runner="${OVERTE_QML_TEST_RUNNER:-$(command -v qmltestrunner 2>/dev/null || true)}"
if [[ -z "$qml_runner" && -x /usr/lib/qt5/bin/qmltestrunner ]]; then
    qml_runner=/usr/lib/qt5/bin/qmltestrunner
fi
if [[ -z "$qml_runner" ]]; then
    printf 'SKIP: qmltestrunner is not installed; QML tests require the project Qt host tools.\n'
    if [[ "${OVERTE_REQUIRE_QML_TESTS:-0}" == 1 ]]; then
        exit 1
    fi
    exit 77
fi

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly android_root="$(cd -- "$script_dir/../.." && pwd)"
readonly report_dir="${OVERTE_TEST_REPORT_DIR:-$android_root/build/test-results}/qml"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
mkdir -p "$report_dir"
temporary_report="$(mktemp "$report_dir/.TEST-qml.XXXXXX.xml")"
trap 'rm -f -- "$temporary_report"' EXIT
set +e
"$qml_runner" -input "$script_dir" \
    -import "$script_dir" -import "$script_dir/imports" \
    -o -,txt -o "$temporary_report,junitxml"
status=$?
set -e
if [[ -s "$temporary_report" ]]; then
    mv -f -- "$temporary_report" "$report_dir/TEST-qml.xml"
fi
exit "$status"
