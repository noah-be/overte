#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
gradle_file="${repo_root}/phone/apps/phoneInterface/build.gradle"
qt_dependencies="${repo_root}/phone/apps/phoneInterface/src/main/res/values/qt_dependencies.xml"

safe_to_trim=(
    Qt5Contacts
    Qt5DocGallery
    Qt5Feedback
    Qt5Organizer
    Qt5QuickParticles
    Qt5Versit
    Qt5VersitOrganizer
)

must_keep=(
    Qt5Test
    Qt5QuickTest
    Qt5PositioningQuick
)

trim_block="$(sed -n '/def unusedPhoneQtRuntimeLibraries = \[/,/^\].collect/p' "${gradle_file}")"
grep -Fq '.collect { "lib${it}_${qtAbiSuffix}.so" }' <<<"${trim_block}" || {
    echo 'phone Qt trim modules must be mapped through the selected ABI suffix' >&2
    exit 1
}

for module in "${safe_to_trim[@]}"; do
    library="lib${module}_arm64-v8a.so"
    count="$(grep -Fo "'${module}'" <<<"${trim_block}" | wc -l)"
    if [[ "${count}" -ne 1 ]]; then
        echo "phone Qt trim list must contain ${module} exactly once" >&2
        exit 1
    fi
    if grep -Fq "${library}" "${qt_dependencies}"; then
        echo "trimmed library is still declared in qt_dependencies.xml: ${library}" >&2
        exit 1
    fi
done

for module in "${must_keep[@]}"; do
    if grep -Fq "'${module}'" <<<"${trim_block}"; then
        echo "transitively required Qt module must not be trimmed: ${module}" >&2
        exit 1
    fi
done

grep -Fq 'include "libQt5PositioningQuick_${qtAbiSuffix}.so"' "${gradle_file}" || {
    echo "required PositioningQuick library is not staged from verified Qt" >&2
    exit 1
}

grep -Eq "tasks\.register\('preparePhoneQtRuntime',[[:space:]]*Sync\)" "${gradle_file}" || {
    echo "phone Qt runtime staging must remove stale legacy files" >&2
    exit 1
}

echo "PASS phone Qt runtime trim policy"
