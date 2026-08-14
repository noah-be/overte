#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$repo_root/ios/v8.env"

work_root="${OVERTE_IOS_V8_WORK_ROOT:-$repo_root/build-ios/v8-work}"
platform="${OVERTE_IOS_V8_PLATFORM:-device}"
case "$platform" in
device)
    sdk_name="iphoneos"
    target_environment="device"
    default_install_root="$repo_root/build-ios/external/v8-ios"
    ;;
simulator)
    sdk_name="iphonesimulator"
    target_environment="simulator"
    default_install_root="$repo_root/build-ios/external/v8-ios-simulator"
    ;;
*)
    echo "build-v8-ios: OVERTE_IOS_V8_PLATFORM must be device or simulator" >&2
    exit 1
    ;;
esac
install_root="${OVERTE_IOS_V8_ROOT:-$default_install_root}"
depot_root="$work_root/depot_tools"
source_root="$work_root/v8"
output_dir="$source_root/out/ios-$target_environment-arm64-jitless"
plan_tool="$repo_root/ios/tools/v8-build-plan.py"
simulator_patch="$repo_root/ios/patches/v8-12.4-jitless-ios-simulator.patch"

die() {
    echo "build-v8-ios: $*" >&2
    exit 1
}

phase_start() {
    v8_phase_name="$1"
    v8_phase_started_at="$(date +%s)"
    echo "v8-phase name=$v8_phase_name state=start utc=$(date -u +%FT%TZ)"
}

phase_finish() {
    local finished_at
    finished_at="$(date +%s)"
    echo "v8-phase name=$v8_phase_name state=complete duration_seconds=$((finished_at - v8_phase_started_at)) utc=$(date -u +%FT%TZ)"
}

resolve_toolchain() {
    command -v xcrun >/dev/null || die "Xcode command-line tools are required"
    host_python="$(command -v python3)"
    xcode_clang="$(xcrun --sdk "$sdk_name" --find clang)"
    xcode_tool_bin="$(dirname "$xcode_clang")"
    xcode_build="$(xcodebuild -version | awk '/Build version/{print $3}')"
    sdk_version="$(xcrun --sdk "$sdk_name" --show-sdk-version)"
    sdk_build="$(xcrun --sdk "$sdk_name" --show-sdk-build-version)"
    compiler_version="$("$xcode_clang" --version | head -n 1)"
    compiler_sha256="$(shasum -a 256 "$xcode_clang" | awk '{print $1}')"
    runner_arch="${RUNNER_ARCH:-$(uname -m)}"
}

write_current_identity() {
    local output_path="$1"
    "$host_python" "$plan_tool" identity \
        --platform "$platform" \
        --runner-arch "$runner_arch" \
        --xcode-build "$xcode_build" \
        --sdk-version "$sdk_version" \
        --sdk-build "$sdk_build" \
        --compiler-version "$compiler_version" \
        --compiler-sha256 "$compiler_sha256" \
        --json-output "$output_path" >/dev/null
}

validate() {
    local archive="$install_root/lib/libv8_monolith.a"
    local metadata="$install_root/share/overte-v8-ios/source.env"
    test -f "$install_root/include/node/v8.h" || die "missing include/node/v8.h"
    test -f "$archive" || die "missing lib/libv8_monolith.a"
    test -f "$install_root/share/overte-v8-ios/build-args.gn" || die "missing build metadata"
    test -f "$install_root/share/overte-v8-ios/compiler.txt" || die "missing compiler metadata"
    test -f "$install_root/share/overte-v8-ios/build-identity.json" || die "missing canonical build identity"
    test -f "$metadata" || die "missing source metadata"
    grep -Fxq "OVERTE_IOS_V8_VERSION=$OVERTE_IOS_V8_VERSION" "$metadata" || die "V8 version metadata mismatch"
    grep -Fxq "OVERTE_IOS_V8_REVISION=$OVERTE_IOS_V8_REVISION" "$metadata" || die "V8 revision metadata mismatch"
    grep -Fxq "OVERTE_IOS_DEPOT_TOOLS_REVISION=$OVERTE_IOS_DEPOT_TOOLS_REVISION" "$metadata" || die "depot_tools metadata mismatch"
    grep -Fxq "OVERTE_IOS_V8_PLATFORM=$platform" "$metadata" || die "V8 platform metadata mismatch"
    grep -Fxq 'target_os = "ios"' "$install_root/share/overte-v8-ios/build-args.gn" || die "archive was not configured for iOS"
    grep -Fxq 'target_cpu = "arm64"' "$install_root/share/overte-v8-ios/build-args.gn" || die "archive was not configured for arm64"
    grep -Fxq "target_environment = \"$target_environment\"" "$install_root/share/overte-v8-ios/build-args.gn" || die "archive was not configured for the selected iOS environment"
    grep -Fxq 'ios_enable_code_signing = false' "$install_root/share/overte-v8-ios/build-args.gn" || die "unsigned static build policy is not recorded"
    grep -Fxq 'use_custom_libcxx = false' "$install_root/share/overte-v8-ios/build-args.gn" || die "Xcode libc++ policy is not recorded"
    grep -Fxq 'clang_use_chrome_plugins = false' "$install_root/share/overte-v8-ios/build-args.gn" || die "Xcode clang plugin policy is not recorded"
    grep -Fxq 'use_lld = false' "$install_root/share/overte-v8-ios/build-args.gn" || die "Xcode linker policy is not recorded"
    grep -q '^Apple clang version ' "$install_root/share/overte-v8-ios/compiler.txt" || die "archive was not built with Apple clang"
    grep -Fxq 'v8_enable_lite_mode = true' "$install_root/share/overte-v8-ios/build-args.gn" || die "JITless lite mode is not recorded"
    grep -Fxq 'v8_jitless = true' "$install_root/share/overte-v8-ios/build-args.gn" || die "JITless mode is not recorded"
    grep -Fxq 'v8_enable_webassembly = false' "$install_root/share/overte-v8-ios/build-args.gn" || die "WebAssembly is not disabled"
    local expected_identity
    expected_identity="$(mktemp "${TMPDIR:-/tmp}/overte-v8-identity.XXXXXX")"
    write_current_identity "$expected_identity"
    if ! cmp -s "$expected_identity" "$install_root/share/overte-v8-ios/build-identity.json"; then
        rm -f "$expected_identity"
        die "canonical V8 build identity does not match this Xcode/SDK/compiler configuration"
    fi
    rm -f "$expected_identity"
    if ! lipo -info "$archive" 2>&1 | grep -Eq '(architecture: arm64|are: arm64$)'; then
        die "archive is not an arm64 Mach-O archive"
    fi
    if lipo -info "$archive" 2>&1 | grep -Eq '\b(x86_64|i386|armv7)\b'; then
        die "archive contains an unsupported architecture"
    fi
    echo "Validated pinned V8 $OVERTE_IOS_V8_VERSION: static iOS $target_environment arm64, JITless, WebAssembly disabled"
}

case "${1:-build}" in
validate)
    resolve_toolchain
    validate
    exit 0
    ;;
stamp-identity)
    resolve_toolchain
    mkdir -p "$install_root/share/overte-v8-ios"
    write_current_identity "$install_root/share/overte-v8-ios/build-identity.json"
    exit 0
    ;;
build)
    ;;
*)
    die "usage: $0 [build|validate|stamp-identity]"
    ;;
esac

phase_start toolchain-probe
resolve_toolchain
mkdir -p "$work_root"
current_identity="$work_root/v8-$target_environment-build-identity.json"
write_current_identity "$current_identity"
phase_finish

phase_start depot-tools
if [[ ! -d "$depot_root/.git" ]]; then
    git clone --filter=blob:none https://chromium.googlesource.com/chromium/tools/depot_tools.git "$depot_root"
fi
git -C "$depot_root" fetch --depth=1 origin "$OVERTE_IOS_DEPOT_TOOLS_REVISION"
git -C "$depot_root" checkout --detach "$OVERTE_IOS_DEPOT_TOOLS_REVISION"
"$depot_root/ensure_bootstrap"
export PATH="$depot_root:$PATH"
export DEPOT_TOOLS_UPDATE=0
phase_finish

phase_start source-sync
if [[ ! -d "$source_root/.git" ]]; then
    git clone --filter=blob:none https://chromium.googlesource.com/v8/v8.git "$source_root"
fi
git -C "$source_root" fetch --depth=1 origin "refs/tags/$OVERTE_IOS_V8_VERSION"
git -C "$source_root" checkout --detach "$OVERTE_IOS_V8_REVISION"

# gclient sync is V8's supported dependency resolver. --revision and the
# detached checkout keep both V8 and its DEPS graph tied to the reviewed tag.
cat > "$work_root/.gclient" <<EOF
solutions = [
  { "name": "v8", "url": "https://chromium.googlesource.com/v8/v8.git", "managed": False,
    "custom_deps": {}, "custom_vars": {} },
]
target_os = ['ios']
EOF
(cd "$work_root" && gclient sync --revision "v8@$OVERTE_IOS_V8_REVISION" --no-history --nohooks)
phase_finish

# V8 12.4 still enables pthread_jit_write_protect_np for an arm64 iOS
# simulator.  Xcode 26.6 explicitly marks that API unavailable there.  This
# package is always JITless, so use the same fail-closed platform capability
# boundary as current V8: pthread JIT write protection is macOS-only.  Accept
# exactly the pinned original or already-patched source state so resumed work
# trees remain deterministic; never transform an unknown revision fuzzily.
phase_start source-patches
if [[ "$platform" == "simulator" ]]; then
    if git -C "$source_root" apply --check "$simulator_patch"; then
        git -C "$source_root" apply "$simulator_patch"
    elif ! git -C "$source_root" apply --reverse --check "$simulator_patch"; then
        die "pinned V8 JITless simulator patch does not match the source tree"
    fi
else
    if git -C "$source_root" apply --reverse --check "$simulator_patch"; then
        git -C "$source_root" apply --reverse "$simulator_patch"
    elif ! git -C "$source_root" apply --check "$simulator_patch"; then
        die "pinned V8 device source state does not match the source tree"
    fi
fi
phase_finish

# V8 12.4's general-purpose runhooks list installs its historical test Python
# environment.  The pinned numpy wheel for that environment was never
# published for macOS arm64 and is unrelated to compiling v8_monolith.  Run
# only the build hooks required by GN/Ninja instead: freeze depot_tools,
# process landmines, install the DEPS-pinned LLVM utilities and generate the
# revision metadata consumed by the build.  The pinned compiler itself is too
# old for Xcode 26's libc++ headers, but its llvm-ar is still required by V8's
# secondary thin-archive toolchain because current Xcode ships no llvm-ar.
phase_start build-hooks
(cd "$source_root" && \
    "$host_python" third_party/depot_tools/update_depot_tools_toggle.py --disable && \
    "$host_python" build/landmines.py --landmine-scripts tools/get_landmines.py && \
    "$host_python" tools/clang/scripts/update.py && \
    "$host_python" build/util/lastchange.py -o build/util/LASTCHANGE)
phase_finish

# Chromium's Apple GN toolchain rebases clang_base_path from nested output
# directories.  A long absolute Xcode path is consequently unsafe, while
# /usr/bin does not expose every LLVM tool on current Xcode runners.  Give GN
# a source-relative directory containing only links to the selected Xcode
# tools so compiler, archiver and inspection commands share one stable base.
xcode_toolchain_dir="$source_root/buildtools/overte-xcode-toolchain/bin"
mkdir -p "$xcode_toolchain_dir"
bundled_llvm_bin="$source_root/third_party/llvm-build/Release+Asserts/bin"
for compiler in clang clang++; do
    compiler_path="$xcode_tool_bin/$compiler"
    test -x "$compiler_path" || die "Xcode compiler is not executable: $compiler_path"
    printf '#!/bin/sh\nexec "%s" "$@"\n' "$compiler_path" > "$xcode_toolchain_dir/$compiler"
    chmod +x "$xcode_toolchain_dir/$compiler"
done
for mapping in \
    "llvm-ar:$bundled_llvm_bin/llvm-ar" \
    "ld64.lld:$bundled_llvm_bin/ld64.lld" \
    "llvm-nm:$(xcrun --find nm)" \
    "llvm-otool:$(xcrun --find otool)" \
    "install_name_tool:$(xcrun --find install_name_tool)"; do
    tool="${mapping%%:*}"
    tool_path="${mapping#*:}"
    test -x "$tool_path" || die "required Apple/LLVM tool is not executable: $tool_path"
    ln -sfn "$tool_path" "$xcode_toolchain_dir/$tool"
done
export PATH="$xcode_toolchain_dir:$PATH"

mkdir -p "$output_dir"
gn_arguments=(gn-args --platform "$platform")
if [[ -n "${OVERTE_IOS_V8_COMPILER_LAUNCHER:-}" ]]; then
    [[ "$OVERTE_IOS_V8_COMPILER_LAUNCHER" == /* && -x "$OVERTE_IOS_V8_COMPILER_LAUNCHER" ]] \
        || die "OVERTE_IOS_V8_COMPILER_LAUNCHER must be an absolute executable path"
    [[ "$OVERTE_IOS_V8_COMPILER_LAUNCHER" != *'"'* && "$OVERTE_IOS_V8_COMPILER_LAUNCHER" != *'\\'* ]] \
        || die "OVERTE_IOS_V8_COMPILER_LAUNCHER contains unsupported characters"
    gn_arguments+=(--compiler-launcher "$OVERTE_IOS_V8_COMPILER_LAUNCHER")
fi
phase_start gn-configure
"$host_python" "$plan_tool" "${gn_arguments[@]}" > "$output_dir/args.gn"
(cd "$source_root" && gn gen "$output_dir")
phase_finish

phase_start compile-v8-monolith
(cd "$source_root" && autoninja -C "$output_dir" v8_monolith)
phase_finish

phase_start package-output
rm -rf "$install_root"
mkdir -p "$install_root/include/node" "$install_root/lib" "$install_root/share/overte-v8-ios"
cp -R "$source_root/include/." "$install_root/include/node/"
cp "$output_dir/obj/libv8_monolith.a" "$install_root/lib/"
cp "$output_dir/args.gn" "$install_root/share/overte-v8-ios/build-args.gn"
cp "$current_identity" "$install_root/share/overte-v8-ios/build-identity.json"
"$xcode_clang" --version > "$install_root/share/overte-v8-ios/compiler.txt"
cp "$source_root/LICENSE.v8" "$install_root/share/overte-v8-ios/"
cat > "$install_root/share/overte-v8-ios/source.env" <<EOF
OVERTE_IOS_V8_VERSION=$OVERTE_IOS_V8_VERSION
OVERTE_IOS_V8_REVISION=$OVERTE_IOS_V8_REVISION
OVERTE_IOS_DEPOT_TOOLS_REVISION=$OVERTE_IOS_DEPOT_TOOLS_REVISION
OVERTE_IOS_V8_PLATFORM=$platform
EOF
phase_finish

phase_start validate-output
validate
phase_finish
