#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
gradle_file="${repo_root}/apps/phoneInterface/build.gradle"
qt_dependencies="${repo_root}/apps/phoneInterface/src/main/res/values/qt_dependencies.xml"

safe_to_trim=(
    libQt5Contacts_arm64-v8a.so
    libQt5DocGallery_arm64-v8a.so
    libQt5Feedback_arm64-v8a.so
    libQt5Organizer_arm64-v8a.so
    libQt5QuickParticles_arm64-v8a.so
    libQt5Versit_arm64-v8a.so
    libQt5VersitOrganizer_arm64-v8a.so
)

must_keep=(
    libQt5Test_arm64-v8a.so
    libQt5QuickTest_arm64-v8a.so
    libQt5PositioningQuick_arm64-v8a.so
)

for library in "${safe_to_trim[@]}"; do
    count="$(grep -Fxc "    '${library}'," "${gradle_file}" || true)"
    if [[ "${library}" == "${safe_to_trim[-1]}" ]]; then
        count="$(grep -Fxc "    '${library}'" "${gradle_file}" || true)"
    fi
    if [[ "${count}" -ne 1 ]]; then
        echo "phone Qt trim list must contain ${library} exactly once" >&2
        exit 1
    fi
    if grep -Fq "${library}" "${qt_dependencies}"; then
        echo "trimmed library is still declared in qt_dependencies.xml: ${library}" >&2
        exit 1
    fi
done

for library in "${must_keep[@]}"; do
    if sed -n '/def unusedPhoneQtRuntimeLibraries = \[/,/^\]/p' "${gradle_file}" |
            grep -Fq "${library}"; then
        echo "transitively required Qt library must not be trimmed: ${library}" >&2
        exit 1
    fi
done

grep -Fq "include 'libQt5PositioningQuick_arm64-v8a.so'" "${gradle_file}" || {
    echo "required PositioningQuick library is not staged from verified Qt" >&2
    exit 1
}

grep -Eq "tasks\.register\('preparePhoneQtRuntime',[[:space:]]*Sync\)" "${gradle_file}" || {
    echo "phone Qt runtime staging must remove stale legacy files" >&2
    exit 1
}

echo "PASS phone Qt runtime trim policy"
