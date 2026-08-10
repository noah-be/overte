#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/phone-build-resource-guard.sh"
phone_build_resource_guard "$script_dir/$(basename -- "${BASH_SOURCE[0]}")" "$@"
profile="$script_dir/conan/profiles/phone-emulator-x86_64"
output_dir="$script_dir/conan/phone-emulator-x86_64-debug"
host_output_dir="$script_dir/conan/phone-emulator-host"
host_tools_dir="$script_dir/pico-host-tools"
ready_sentinel="$output_dir/.phone-emulator-dependencies.ready"
android_sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}"
export ANDROID_SDK_ROOT="$android_sdk"
export ANDROID_HOME="$android_sdk"
export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-$android_sdk/ndk/27.3.13750724}"
export TMPDIR="${PHONE_EMULATOR_TMPDIR:-$script_dir/build/phone-emulator/tmp}"

fail() {
    echo "error: $*" >&2
    exit 2
}

[[ -d "$ANDROID_NDK_HOME" ]] || fail "Android NDK 27.3.13750724 was not found"
command -v conan >/dev/null 2>&1 || fail "Conan 2 was not found"
conan --version | grep -q '^Conan version 2\.' || fail "Conan 2 is required"
mkdir -p -- "$TMPDIR"

rm -f -- "$ready_sentinel"
conan export "$script_dir/conan/recipes/libnode"
conan export "$script_dir/conan/recipes/onetbb-local" --version=2021.10.0
conan export "$script_dir/conan/recipes/nvidia-texture-tools" --version=2023.01

conan install "$script_dir/conan/conanfile-pico-host-tools.py" \
    -of "$host_output_dir" \
    -pr:h default \
    -pr:b default \
    --build=missing
host_graph="$host_output_dir/graph.json"
conan graph info "$script_dir/conan/conanfile-pico-host-tools.py" \
    -pr:h default -pr:b default --format=json --out-file="$host_graph"

package_folder() {
    local package="$1" reference folder
    reference="$(python3 - "$host_graph" "$package" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as graph_file:
    nodes = json.load(graph_file)["graph"]["nodes"].values()
prefix = sys.argv[2] + "/"
for node in nodes:
    reference = node.get("ref") or ""
    if reference.startswith(prefix):
        print(f"{reference}:{node['package_id']}")
        break
else:
    raise SystemExit(1)
PY
)" || fail "Host package metadata is missing: $package"
    folder="$(conan cache path "$reference")"
    [[ -d "$folder" ]] || fail "Host package folder is missing: $package"
    printf '%s\n' "$folder"
}

mkdir -p -- "$host_tools_dir"
ln -sfn "$(package_folder glslang)/bin/glslang" \
    "$host_tools_dir/glslangValidator"
ln -sfn "$(package_folder scribe)/tools/scribe" "$host_tools_dir/scribe"
ln -sfn "$(package_folder spirv-cross)/bin/spirv-cross" \
    "$host_tools_dir/spirv-cross"
ln -sfn "$(package_folder spirv-tools)/bin/spirv-opt" \
    "$host_tools_dir/spirv-opt"
for tool in glslangValidator scribe spirv-cross spirv-opt; do
    [[ -x "$host_tools_dir/$tool" ]] || fail "Host tool is not executable: $tool"
done

conan install "$script_dir/conan/conanfile-pico.py" \
    -of "$output_dir" \
    -pr:h "$profile" \
    -pr:b default \
    --build=missing

generator="$(find "$output_dir/generators" -maxdepth 1 -type f \
    -name 'Qt5-debug-*-data.cmake' -print -quit)"
[[ -n "$generator" ]] || fail "Qt generator metadata was not produced"
qt_dir="$(sed -n 's/set(qt_PACKAGE_FOLDER_DEBUG "\([^"]*\)")/\1/p' "$generator")"
[[ -d "$qt_dir" ]] || fail "Qt x86_64 package directory was not produced"
find "$qt_dir" -type f -name '*x86_64.so' -print -quit | grep -q . \
    || fail "Qt package contains no x86_64 Android libraries"

mkdir -p -- "$output_dir"
printf 'abi=x86_64\nprofile=%s\n' "$(sha256sum "$profile" | awk '{print $1}')" \
    > "$ready_sentinel.tmp"
mv -- "$ready_sentinel.tmp" "$ready_sentinel"
echo "Phone emulator dependencies are ready: $output_dir"
