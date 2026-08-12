#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly app="${1:?usage: verify-bundle-freshness.sh /path/to/Overte.app /path/to/build}"
readonly build_root="${2:?usage: verify-bundle-freshness.sh /path/to/Overte.app /path/to/build}"
readonly bundled="$app/Contents/Frameworks/libgpu-gl.dylib"
readonly built="$(find "$build_root/libraries/gpu-gl" -type f -name libgpu-gl.dylib -print -quit)"

fail() {
    echo "macOS bundle freshness check failed: $1" >&2
    exit 1
}

[[ -n "$built" && -f "$built" ]] || fail "build-tree libgpu-gl.dylib is missing"
[[ -f "$bundled" ]] || fail "bundled libgpu-gl.dylib is missing"
command -v dwarfdump >/dev/null 2>&1 || fail "dwarfdump is unavailable"
command -v strings >/dev/null 2>&1 || fail "strings is unavailable"

uuid() {
    LC_ALL=C dwarfdump --uuid "$1" | awk '{ print $2 " " $3 }'
}

readonly built_uuid="$(uuid "$built")"
readonly bundled_uuid="$(uuid "$bundled")"
[[ -n "$built_uuid" ]] || fail "build-tree libgpu-gl.dylib has no Mach-O UUID"
[[ "$built_uuid" == "$bundled_uuid" ]] || fail "bundle contains a stale libgpu-gl.dylib"

# The current renderer diagnostic is deliberately bounded and lets runtime
# failures identify the exact first-draw program. Its presence also proves the
# dylib copied into the app came from this source generation.
strings -a "$bundled" | grep -Fq "OVERTE_MACOS_GL_DRAW begin" \
    || fail "bundled renderer lacks the current first-draw diagnostic"

echo "macOS bundle internal-library freshness valid"
