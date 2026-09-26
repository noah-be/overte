#!/usr/bin/env bash
set -euo pipefail
mode="${1:?Expected core or full}"
build_dir="${OVERTE_NATIVE_BUILD_DIR:-build/native}"
case "$mode" in core|full) ;; *) echo 'Invalid native mode' >&2; exit 2;; esac
if [[ -f "$build_dir/.native-mode" ]] && [[ "$(cat "$build_dir/.native-mode")" != "$mode" ]]; then
  echo 'Native mode changed; use a fresh build/native directory to avoid mixed toolchains.' >&2
  exit 2
fi
mkdir -p "$build_dir/.cmake/api/v1/query"
: > "$build_dir/.cmake/api/v1/query/codemodel-v2"
common=(-S . -B "$build_dir" -G Ninja -DCMAKE_BUILD_TYPE=Release
  -DCMAKE_CXX_COMPILER_LAUNCHER=ccache -DCMAKE_C_COMPILER_LAUNCHER=ccache
  -DOVERTE_BUILD_TESTS=ON -DOVERTE_BUILD_MANUAL_TESTS=OFF
  -DOVERTE_NATIVE_CI=ON -DOVERTE_BUILD_INSTALLER=OFF)
if [[ "$mode" == core ]]; then
  cmake "${common[@]}" -DOVERTE_BUILD_CLIENT=OFF -DOVERTE_BUILD_SERVER=OFF -DOVERTE_BUILD_TOOLS=OFF \
    -DOVERTE_TEST_GROUPS=shared -DOVERTE_USE_SYSTEM_LIBS=ON
else
  groups="$(python3 -c 'import json; print(";".join(sorted({name.rsplit("-", 1)[0] for name in json.load(open(".github/native-tests.json"))["tests"]})))')"
  cmake "${common[@]}" -DOVERTE_BUILD_CLIENT=ON -DOVERTE_BUILD_SERVER=ON -DOVERTE_BUILD_TOOLS=ON \
    -DOVERTE_USE_SYSTEM_LIBS=OFF "-DOVERTE_TEST_GROUPS=$groups" \
    -DCMAKE_TOOLCHAIN_FILE=generators/conan_toolchain.cmake
fi

printf '%s\n' "$mode" > "$build_dir/.native-mode"
