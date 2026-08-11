#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$repo_root/ios/v8.env"

work_root="${OVERTE_IOS_V8_WORK_ROOT:-$repo_root/build-ios/v8-work}"
install_root="${OVERTE_IOS_V8_ROOT:-$repo_root/build-ios/external/v8-ios}"
depot_root="$work_root/depot_tools"
source_root="$work_root/v8"
output_dir="$source_root/out/ios-arm64-jitless"

die() {
    echo "build-v8-ios: $*" >&2
    exit 1
}

validate() {
    local archive="$install_root/lib/libv8_monolith.a"
    local metadata="$install_root/share/overte-v8-ios/source.env"
    test -f "$install_root/include/node/v8.h" || die "missing include/node/v8.h"
    test -f "$archive" || die "missing lib/libv8_monolith.a"
    test -f "$install_root/share/overte-v8-ios/build-args.gn" || die "missing build metadata"
    test -f "$install_root/share/overte-v8-ios/compiler.txt" || die "missing compiler metadata"
    test -f "$metadata" || die "missing source metadata"
    grep -Fxq "OVERTE_IOS_V8_VERSION=$OVERTE_IOS_V8_VERSION" "$metadata" || die "V8 version metadata mismatch"
    grep -Fxq "OVERTE_IOS_V8_REVISION=$OVERTE_IOS_V8_REVISION" "$metadata" || die "V8 revision metadata mismatch"
    grep -Fxq "OVERTE_IOS_DEPOT_TOOLS_REVISION=$OVERTE_IOS_DEPOT_TOOLS_REVISION" "$metadata" || die "depot_tools metadata mismatch"
    grep -Fxq 'target_os = "ios"' "$install_root/share/overte-v8-ios/build-args.gn" || die "archive was not configured for iOS"
    grep -Fxq 'target_cpu = "arm64"' "$install_root/share/overte-v8-ios/build-args.gn" || die "archive was not configured for arm64"
    grep -Fxq 'target_environment = "device"' "$install_root/share/overte-v8-ios/build-args.gn" || die "archive was not configured for an iOS device"
    grep -Fxq 'ios_enable_code_signing = false' "$install_root/share/overte-v8-ios/build-args.gn" || die "unsigned static build policy is not recorded"
    grep -Fxq 'use_custom_libcxx = false' "$install_root/share/overte-v8-ios/build-args.gn" || die "Xcode libc++ policy is not recorded"
    grep -Fxq 'clang_use_chrome_plugins = false' "$install_root/share/overte-v8-ios/build-args.gn" || die "Xcode clang plugin policy is not recorded"
    grep -Fxq 'use_lld = false' "$install_root/share/overte-v8-ios/build-args.gn" || die "Xcode linker policy is not recorded"
    grep -q '^Apple clang version ' "$install_root/share/overte-v8-ios/compiler.txt" || die "archive was not built with Apple clang"
    grep -Fxq 'v8_enable_lite_mode = true' "$install_root/share/overte-v8-ios/build-args.gn" || die "JITless lite mode is not recorded"
    grep -Fxq 'v8_jitless = true' "$install_root/share/overte-v8-ios/build-args.gn" || die "JITless mode is not recorded"
    grep -Fxq 'v8_enable_webassembly = false' "$install_root/share/overte-v8-ios/build-args.gn" || die "WebAssembly is not disabled"
    if ! lipo -info "$archive" 2>&1 | grep -Eq '(architecture: arm64|are: arm64$)'; then
        die "archive is not an arm64 Mach-O archive"
    fi
    if lipo -info "$archive" 2>&1 | grep -Eq '\b(x86_64|i386|armv7)\b'; then
        die "archive contains a non-device architecture"
    fi
    echo "Validated pinned V8 $OVERTE_IOS_V8_VERSION: static iOS arm64, JITless, WebAssembly disabled"
}

case "${1:-build}" in
validate)
    validate
    exit 0
    ;;
build)
    ;;
*)
    die "usage: $0 [build|validate]"
    ;;
esac

command -v xcrun >/dev/null || die "Xcode command-line tools are required"
host_python="$(command -v python3)"
xcode_clang="$(xcrun --sdk iphoneos --find clang)"
xcode_tool_bin="$(dirname "$xcode_clang")"
mkdir -p "$work_root"

if [[ ! -d "$depot_root/.git" ]]; then
    git clone --filter=blob:none https://chromium.googlesource.com/chromium/tools/depot_tools.git "$depot_root"
fi
git -C "$depot_root" fetch --depth=1 origin "$OVERTE_IOS_DEPOT_TOOLS_REVISION"
git -C "$depot_root" checkout --detach "$OVERTE_IOS_DEPOT_TOOLS_REVISION"
"$depot_root/ensure_bootstrap"
export PATH="$depot_root:$PATH"
export DEPOT_TOOLS_UPDATE=0

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

# V8 12.4's general-purpose runhooks list installs its historical test Python
# environment.  The pinned numpy wheel for that environment was never
# published for macOS arm64 and is unrelated to compiling v8_monolith.  Run
# only the build hooks required by GN/Ninja instead: freeze depot_tools,
# process landmines and generate the revision metadata consumed by the build.
# The target compiler is selected explicitly from Xcode below; downloading
# V8's historical Clang would be both unused and incompatible with Xcode 26's
# libc++ headers.
(cd "$source_root" && \
    "$host_python" third_party/depot_tools/update_depot_tools_toggle.py --disable && \
    "$host_python" build/landmines.py --landmine-scripts tools/get_landmines.py && \
    "$host_python" build/util/lastchange.py -o build/util/LASTCHANGE)

# Chromium's Apple GN toolchain rebases clang_base_path from nested output
# directories.  A long absolute Xcode path is consequently unsafe, while
# /usr/bin does not expose every LLVM tool on current Xcode runners.  Give GN
# a source-relative directory containing only links to the selected Xcode
# tools so compiler, archiver and inspection commands share one stable base.
xcode_toolchain_dir="$source_root/buildtools/overte-xcode-toolchain/bin"
mkdir -p "$xcode_toolchain_dir"
for tool in clang clang++ llvm-ar llvm-nm llvm-otool install_name_tool; do
    case "$tool" in
    install_name_tool)
        tool_path="$(xcrun --find install_name_tool)"
        ;;
    *)
        tool_path="$xcode_tool_bin/$tool"
        ;;
    esac
    test -x "$tool_path" || die "Xcode tool is not executable: $tool_path"
    ln -sfn "$tool_path" "$xcode_toolchain_dir/$tool"
done

mkdir -p "$output_dir"
cat > "$output_dir/args.gn" <<EOF
target_os = "ios"
target_cpu = "arm64"
target_environment = "device"
ios_deployment_target = "$OVERTE_IOS_V8_DEPLOYMENT_TARGET"
ios_enable_code_signing = false
is_debug = false
is_component_build = false
use_custom_libcxx = false
clang_base_path = "//buildtools/overte-xcode-toolchain"
clang_use_chrome_plugins = false
use_lld = false
symbol_level = 0
strip_debug_info = true
v8_monolithic = true
v8_use_external_startup_data = false
v8_enable_i18n_support = false
v8_enable_lite_mode = true
v8_jitless = true
v8_enable_webassembly = false
v8_enable_pointer_compression = false
treat_warnings_as_errors = false
EOF

(cd "$source_root" && gn gen "$output_dir" && autoninja -C "$output_dir" v8_monolith)

rm -rf "$install_root"
mkdir -p "$install_root/include/node" "$install_root/lib" "$install_root/share/overte-v8-ios"
cp -R "$source_root/include/." "$install_root/include/node/"
cp "$output_dir/obj/libv8_monolith.a" "$install_root/lib/"
cp "$output_dir/args.gn" "$install_root/share/overte-v8-ios/build-args.gn"
"$xcode_clang" --version > "$install_root/share/overte-v8-ios/compiler.txt"
cp "$source_root/LICENSE.v8" "$install_root/share/overte-v8-ios/"
cat > "$install_root/share/overte-v8-ios/source.env" <<EOF
OVERTE_IOS_V8_VERSION=$OVERTE_IOS_V8_VERSION
OVERTE_IOS_V8_REVISION=$OVERTE_IOS_V8_REVISION
OVERTE_IOS_DEPOT_TOOLS_REVISION=$OVERTE_IOS_DEPOT_TOOLS_REVISION
EOF

validate
