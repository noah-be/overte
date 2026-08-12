#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly app="${1:?usage: verify-glad-linkage.sh /path/to/Overte.app}"
readonly frameworks="$app/Contents/Frameworks"

fail() { echo "macOS bundle linkage error: $*" >&2; exit 1; }

[[ -d "$app" ]] || fail "application bundle does not exist: $app"
[[ -d "$frameworks" ]] || fail "Frameworks directory does not exist: $frameworks"

glad_libraries=()
while IFS= read -r library; do
    glad_libraries+=("$library")
done < <(find "$frameworks" -maxdepth 1 -type f -name 'libglad*.dylib' -print)

[[ "${#glad_libraries[@]}" -eq 1 ]] \
    || fail "expected exactly one shared libglad dylib, found ${#glad_libraries[@]}"

readonly consumers=(
    "$app/Contents/MacOS/Overte"
    "$frameworks/libgl.dylib"
    "$frameworks/libdisplay-plugins.dylib"
)

for consumer in "${consumers[@]}"; do
    [[ -f "$consumer" ]] || fail "required GLAD consumer is missing: $consumer"
    otool -L "$consumer" | grep -Eq '@rpath/libglad[^/]*\.dylib' \
        || fail "consumer does not bind to the bundled shared GLAD: $consumer"
    if nm -gU "$consumer" 2>/dev/null \
        | grep -Eq '(_glad_glGetString|_glad_debug_impl_glGetString)'; then
        fail "consumer embeds a second GLAD function-pointer table: $consumer"
    fi
done

echo "macOS GLAD linkage valid: ${glad_libraries[0]}"

readonly webengine_helper="$frameworks/QtWebEngineCore.framework/Helpers/QtWebEngineProcess.app/Contents/MacOS/QtWebEngineProcess"
readonly qt_gui="$frameworks/QtGui.framework/Versions/5/QtGui"
[[ -x "$webengine_helper" ]] || fail "QtWebEngine helper is missing or not executable"
[[ -f "$qt_gui" ]] || fail "QtGui framework required by QtWebEngine is missing"
otool -L "$webengine_helper" | grep -Fq '@rpath/QtGui.framework/Versions/5/QtGui' \
    || fail "QtWebEngine helper has no relocatable QtGui dependency"
otool -l "$webengine_helper" | grep -Fq '@executable_path/../../../../..' \
    || fail "QtWebEngine helper cannot reach the main Frameworks directory"

echo "macOS QtWebEngine helper linkage valid"
