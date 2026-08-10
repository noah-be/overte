#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly build_type="${OVERTE_MACOS_BUILD_TYPE:-RelWithDebInfo}"
readonly architecture="${OVERTE_MACOS_ARCH:-x86_64}"
readonly qt_source="${OVERTE_MACOS_QT_SOURCE:-aqt}"
readonly build_dir="${OVERTE_MACOS_BUILD_DIR:-$source_root/build}"

fail() { echo "macOS build error: $*" >&2; exit 1; }
note() { echo "macOS build: $*"; }
require_macos() { [[ "$(uname -s)" == "Darwin" ]] || fail "this command must run on macOS"; }

doctor() {
    require_macos
    command -v xcodebuild >/dev/null || fail "Xcode command-line tools are missing"
    command -v cmake >/dev/null || fail "CMake is missing"
    command -v conan >/dev/null || fail "Conan 2 is missing"
    command -v python3 >/dev/null || fail "Python 3 is missing"
    command -v node >/dev/null || fail "Node.js is missing"
    [[ "$(conan --version)" =~ Conan\ version\ 2\. ]] || fail "Conan 2 is required"
    case "$architecture" in x86_64|arm64) ;; *) fail "OVERTE_MACOS_ARCH must be x86_64 or arm64" ;; esac
    note "Xcode: $(xcodebuild -version | tr '\n' ' ')"
    note "host: $(uname -m); target: $architecture; configuration: $build_type"
    note "Qt source: $qt_source; deployment target: ${MACOSX_DEPLOYMENT_TARGET:-11.0}"
}

ensure_conan_profile() {
    conan profile path default >/dev/null 2>&1 || conan profile detect --name default
}

configure_remotes() {
    conan remote add overte https://artifactory.overte.org/artifactory/api/conan/overte --force
    conan remote update conancenter --url https://artifactory.overte.org/artifactory/api/conan/conan-center
}

conan_architecture() { [[ "$architecture" == arm64 ]] && echo armv8 || echo x86_64; }

deps() {
    doctor
    ensure_conan_profile
    configure_remotes
    if [[ "$qt_source" == aqt ]]; then
        # The published aqt recipe selects a Windows archive on macOS and does
        # not preserve the installer's executable bit. Export our macOS-only
        # repair under the same reference before resolving the graph.
        conan export "$source_root/macos/conan/qt-aqt" --user overte --channel aqt
    fi
    mkdir -p "$build_dir"
    local args=("$source_root" -s "arch=$(conan_architecture)" -s compiler.cppstd=20
        -s "build_type=$build_type" -o "Overte/*:qt_source=$qt_source" -b missing -of "$build_dir")
    # Some legacy recipes only expose OpenSSL correctly on the second graph resolution.
    conan install "${args[@]}"
    conan install "${args[@]}"
}

configure() {
    doctor
    local preset="conan-$(printf '%s' "$build_type" | tr '[:upper:]' '[:lower:]')"
    cmake --preset "$preset" \
        -DOVERTE_RENDERING_BACKEND=OpenGL -DOVERTE_BUILD_CLIENT=ON \
        -DOVERTE_BUILD_SERVER=OFF -DOVERTE_BUILD_TOOLS=OFF \
        -DOVERTE_BUILD_TESTS=OFF -DOVERTE_BUILD_INSTALLER=OFF \
        -DOVERTE_RELEASE_TYPE=DEV -DCMAKE_OSX_ARCHITECTURES="$architecture" \
        -DCMAKE_OSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-11.0}"
}

build() {
    configure
    local preset="conan-$(printf '%s' "$build_type" | tr '[:upper:]' '[:lower:]')"
    cmake --build --preset "$preset" --target Overte --parallel "$(sysctl -n hw.logicalcpu)"
    find "$build_dir" -type d -name Overte.app -print -quit
}

case "${1:-}" in
    doctor) doctor ;; deps) deps ;; configure) configure ;; build) build ;; all) deps; build ;;
    *) echo "Usage: macos/build-macos.sh doctor|deps|configure|build|all" >&2; exit 2 ;;
esac
