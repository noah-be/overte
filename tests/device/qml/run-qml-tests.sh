#!/usr/bin/env bash
set -euo pipefail

qml_runner="${OVERTE_QML_TEST_RUNNER:-$(command -v qmltestrunner 2>/dev/null || true)}"
if [[ -z "$qml_runner" ]]; then
    printf 'SKIP: qmltestrunner is not installed; QML tests require the project Qt host tools.\n'
    exit 77
fi

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../../.." && pwd)"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
"$qml_runner" -input "$script_dir" \
    -import "$repo_root/interface/resources/qml" \
    -import "$repo_root/scripts/system/settings/qml" \
    -o -,txt
