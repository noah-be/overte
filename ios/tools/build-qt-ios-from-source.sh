#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../.." && pwd)"
readonly prepare="$script_dir/prepare-qt-ios.sh"

# shellcheck disable=SC1091
source "$repo_root/ios/versions.env"

work_root=""
install_root=""
archive=""
jobs="$(sysctl -n hw.logicalcpu 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
print_plan=0
stage="all"
target_sdk="iphoneos"

die() {
    echo "error: $*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Usage: build-qt-ios-from-source.sh --work-root ABSOLUTE_PATH \
       --install-root ABSOLUTE_PATH [--archive FILE] [--jobs NUMBER] \
       [--stage source|host|ios|all] [--target-sdk iphoneos|iphonesimulator] \
       [--print-plan]

Builds a resumable stage of the pinned minimal Qt host and iOS SDK. Existing
configured build trees are resumed. Completed, validated installations are
reused. The ios stage requires an already validated host installation.
EOF
}

while (($#)); do
    case "$1" in
        --work-root) work_root="${2:-}"; shift 2 ;;
        --install-root) install_root="${2:-}"; shift 2 ;;
        --archive) archive="${2:-}"; shift 2 ;;
        --jobs) jobs="${2:-}"; shift 2 ;;
        --stage) stage="${2:-}"; shift 2 ;;
        --target-sdk) target_sdk="${2:-}"; shift 2 ;;
        --print-plan) print_plan=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) die "unknown argument: $1" ;;
    esac
done

[[ "$work_root" == /* ]] || die "--work-root must be an absolute path"
[[ "$install_root" == /* ]] || die "--install-root must be an absolute path"
[[ "$work_root" != "$install_root" ]] || die "work and install roots must differ"
[[ "$work_root" != "/" && "$install_root" != "/" ]] || die "filesystem root is not a valid build path"
case "$work_root/" in "$install_root/"*) die "work root must not be inside install root" ;; esac
case "$install_root/" in "$work_root/"*) die "install root must not be inside work root" ;; esac
[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || die "--jobs must be a positive integer"
case "$stage" in source|host|ios|all) ;; *) die "--stage must be source, host, ios, or all" ;; esac
case "$target_sdk" in iphoneos|iphonesimulator) ;; *) die "--target-sdk must be iphoneos or iphonesimulator" ;; esac

readonly qt_version="${OVERTE_IOS_QT_VERSION:?missing OVERTE_IOS_QT_VERSION}"
readonly modules="qtbase,qtdeclarative,qtmultimedia,qtsvg,qtwebchannel,qtwebsockets,qtwebview,qt5compat,qtshadertools"
readonly source_name="qt-everywhere-src-${qt_version}"
readonly downloads="$work_root/downloads"
readonly source_root="$work_root/source/$source_name"
readonly host_build="$work_root/build-host"
readonly ios_build="$work_root/build-$target_sdk"
readonly host_prefix="$install_root/macos"
readonly ios_prefix="$install_root/ios"
readonly archive_path="${archive:-$downloads/${source_name}.tar.xz}"

manifest_value() {
    local key="$1"
    "$prepare" manifest | sed -n "s/^${key}=//p"
}

readonly source_url="$(manifest_value QT_SOURCE_URL)"
readonly source_sha256="$(manifest_value QT_SOURCE_SHA256)"
readonly host_plan_id="qt-${qt_version}-modules-${modules//,/-}-ios-min-${OVERTE_IOS_MIN_VERSION}"
ios_plan_id="${host_plan_id}-skip-qtwebengine"
if [[ "$target_sdk" == "iphonesimulator" ]]; then
    ios_plan_id="${ios_plan_id}-iphonesimulator"
fi
readonly ios_plan_id

print_build_plan() {
    printf 'PLAN_ID=%s\nHOST_PLAN_ID=%s\nIOS_PLAN_ID=%s\nTARGET_SDK=%s\nQT_VERSION=%s\nMODULES=%s\nQT_SOURCE_URL=%s\nQT_SOURCE_SHA256=%s\n' \
        "$ios_plan_id" "$host_plan_id" "$ios_plan_id" "$target_sdk" "$qt_version" "$modules" "$source_url" "$source_sha256"
    printf 'WORK_ROOT=%s\nHOST_PREFIX=%s\nIOS_PREFIX=%s\n' \
        "$work_root" "$host_prefix" "$ios_prefix"
}

if ((print_plan)); then
    print_build_plan
    exit 0
fi

[[ "$(uname -s)" == "Darwin" ]] || die "Qt for iOS must be built on macOS with Xcode"
command -v curl >/dev/null || die "curl is required"
command -v cmake >/dev/null || die "cmake is required"
command -v xcodebuild >/dev/null || die "Xcode is required"
command -v ninja >/dev/null || die "ninja is required"

mkdir -p "$downloads" "$work_root/source" "$host_build" "$ios_build" "$install_root"

ensure_source() {
    local partial extract_stamp

    if [[ -z "$archive" && ! -f "$archive_path" ]]; then
        partial="$archive_path.partial"
        curl --fail --location --retry 5 --retry-all-errors \
            --continue-at - --output "$partial" "$source_url"
        mv "$partial" "$archive_path"
    fi
    "$prepare" verify-source "$archive_path"

    extract_stamp="$work_root/source/.${source_name}.${source_sha256}.extracted"
    if [[ -f "$extract_stamp" ]]; then
        [[ -x "$source_root/configure" ]] ||
            die "source extraction stamp exists without a usable configure script: $extract_stamp"
        return
    fi
    [[ ! -e "$source_root" ]] ||
        die "source tree exists without matching extraction stamp: $source_root"
    tar -xJf "$archive_path" -C "$work_root/source"
    [[ -x "$source_root/configure" ]] || die "Qt source archive did not contain configure"
    touch "$extract_stamp"
}

configure_tree() {
    local kind="$1" build="$2" prefix="$3"
    shift 3
    local selected_plan_id="$host_plan_id"
    [[ "$kind" != "ios" ]] || selected_plan_id="$ios_plan_id"
    local stamp="$build/.overte-${selected_plan_id}-${kind}.configured"
    if [[ ! -f "$stamp" ]]; then
        if [[ -f "$build/CMakeCache.txt" ]]; then
            die "$kind build tree has an unknown configuration: $build"
        fi
        "$source_root/configure" -submodules "$modules" -release \
            -nomake examples -nomake tests -prefix "$prefix" "$@"
        touch "$stamp"
    fi
}

build_with_live_compiler_tracking() {
    local build_dir="$1"
    local live_log="$build_dir/.overte-compiler-watchdog.jsonl"
    : > "$live_log"
    export OVERTE_COMPILER_WATCHDOG_LOG="$live_log"
    tail -n 0 -F "$live_log" &
    local tail_pid=$!
    cmake --build . --parallel "$jobs" &
    local build_pid=$!
    "$repo_root/ios/ci/build-heartbeat.py" \
        --root-pid "$build_pid" --log "$live_log" --interval 30 &
    local heartbeat_pid=$!
    local status=0
    if wait "$build_pid"; then
        status=0
    else
        status=$?
    fi
    sleep 1
    kill "$heartbeat_pid" 2>/dev/null || true
    wait "$heartbeat_pid" 2>/dev/null || true
    kill "$tail_pid" 2>/dev/null || true
    wait "$tail_pid" 2>/dev/null || true
    unset OVERTE_COMPILER_WATCHDOG_LOG
    return "$status"
}

build_host() {
    if "$prepare" validate-host "$host_prefix" >/dev/null 2>&1; then
        [[ "$(cat "$host_prefix/.overte-qt-host-plan-id" 2>/dev/null || true)" == "$host_plan_id" ]] ||
            die "validated host prefix has missing or mismatched build-plan provenance: $host_prefix"
        printf 'Reusing validated Qt host installation: %s\n' "$host_prefix"
        return
    fi
    [[ ! -e "$host_prefix" ]] ||
        die "host prefix exists but is not a validated Qt host installation: $host_prefix"

    cd "$host_build"
    local compiler_watchdog="$repo_root/ios/ci/compiler-watchdog.py"
    if command -v sccache >/dev/null 2>&1; then
        configure_tree host "$host_build" "$host_prefix" -- \
            -D "CMAKE_C_COMPILER_LAUNCHER=$compiler_watchdog;--" \
            -D "CMAKE_CXX_COMPILER_LAUNCHER=$compiler_watchdog;--" \
            -D "CMAKE_OBJC_COMPILER_LAUNCHER=$compiler_watchdog;--" \
            -D "CMAKE_OBJCXX_COMPILER_LAUNCHER=$compiler_watchdog;--"
    else
        configure_tree host "$host_build" "$host_prefix"
    fi
    build_with_live_compiler_tracking "$host_build"
    cmake --install .
    "$prepare" validate-host "$host_prefix"
    printf '%s\n' "$host_plan_id" > "$host_prefix/.overte-qt-host-plan-id"
}

build_ios() {
    "$prepare" validate-host "$host_prefix" >/dev/null
    if "$prepare" validate-target "$ios_prefix" >/dev/null 2>&1; then
        [[ "$(cat "$ios_prefix/.overte-qt-ios-plan-id" 2>/dev/null || true)" == "$ios_plan_id" ]] ||
            die "validated iOS prefix has missing or mismatched build-plan provenance: $ios_prefix"
        printf 'Reusing validated Qt iOS installation: %s\n' "$ios_prefix"
        "$prepare" validate "$ios_prefix" "$host_prefix" >/dev/null
        return
    fi
    [[ ! -e "$ios_prefix" ]] ||
        die "iOS prefix exists but is not a validated Qt target installation: $ios_prefix"

    cd "$ios_build"
    local compiler_watchdog="$repo_root/ios/ci/compiler-watchdog.py"
    if command -v sccache >/dev/null 2>&1; then
        configure_tree ios "$ios_build" "$ios_prefix" \
            -skip qtwebengine -platform macx-ios-clang -sdk "$target_sdk" -qt-host-path "$host_prefix" -- \
            -D "CMAKE_OSX_DEPLOYMENT_TARGET=$OVERTE_IOS_MIN_VERSION" \
            -D "CMAKE_C_COMPILER_LAUNCHER=$compiler_watchdog;--" \
            -D "CMAKE_CXX_COMPILER_LAUNCHER=$compiler_watchdog;--" \
            -D "CMAKE_OBJC_COMPILER_LAUNCHER=$compiler_watchdog;--" \
            -D "CMAKE_OBJCXX_COMPILER_LAUNCHER=$compiler_watchdog;--"
    else
        configure_tree ios "$ios_build" "$ios_prefix" \
            -skip qtwebengine -platform macx-ios-clang -sdk "$target_sdk" -qt-host-path "$host_prefix" \
            -- -D "CMAKE_OSX_DEPLOYMENT_TARGET=$OVERTE_IOS_MIN_VERSION"
    fi
    build_with_live_compiler_tracking "$ios_build"
    cmake --install .
    "$prepare" validate-target "$ios_prefix"
    "$prepare" validate "$ios_prefix" "$host_prefix"
    printf '%s\n' "$ios_plan_id" > "$ios_prefix/.overte-qt-ios-plan-id"
}

ensure_source
case "$stage" in
    source) ;;
    host) build_host ;;
    ios) build_ios ;;
    all)
        build_host
        build_ios
        ;;
esac

if [[ "$stage" == "all" ]]; then
    "$prepare" validate "$ios_prefix" "$host_prefix"
    printf '%s\n' "$ios_plan_id" > "$install_root/.overte-qt-ios-plan-id"
fi
