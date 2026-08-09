#!/usr/bin/env bash
set -euo pipefail

qml_runner="$(command -v qmltestrunner 2>/dev/null || true)"
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
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
exec "$qml_runner" -input "$script_dir" \
    -import "$script_dir" -import "$script_dir/imports"
