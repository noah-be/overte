#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly build_type="${OVERTE_MACOS_BUILD_TYPE:-RelWithDebInfo}"
readonly architecture="${OVERTE_MACOS_ARCH:-x86_64}"
readonly qt_source="${OVERTE_MACOS_QT_SOURCE:-aqt}"
readonly build_dir="${OVERTE_MACOS_BUILD_DIR:-$source_root/build}"
readonly build_tests="${OVERTE_MACOS_BUILD_TESTS:-OFF}"
readonly requested_build_jobs="${OVERTE_MACOS_BUILD_JOBS:-}"

fail() { echo "macOS build error: $*" >&2; exit 1; }
note() { echo "macOS build: $*"; }
require_macos() { [[ "$(uname -s)" == "Darwin" ]] || fail "this command must run on macOS"; }
effective_build_jobs() {
    if [[ -n "$requested_build_jobs" ]]; then
        printf '%s\n' "$requested_build_jobs"
    else
        sysctl -n hw.logicalcpu
    fi
}

doctor() {
    require_macos
    command -v xcodebuild >/dev/null || fail "Xcode command-line tools are missing"
    command -v cmake >/dev/null || fail "CMake is missing"
    command -v ninja >/dev/null || fail "Ninja is missing"
    command -v conan >/dev/null || fail "Conan 2 is missing"
    command -v python3 >/dev/null || fail "Python 3 is missing"
    command -v node >/dev/null || fail "Node.js is missing"
    [[ "$(conan --version)" =~ Conan\ version\ 2\. ]] || fail "Conan 2 is required"
    case "$architecture" in x86_64|arm64) ;; *) fail "OVERTE_MACOS_ARCH must be x86_64 or arm64" ;; esac
    case "$build_tests" in ON|OFF) ;; *) fail "OVERTE_MACOS_BUILD_TESTS must be ON or OFF" ;; esac
    [[ -z "$requested_build_jobs" || "$requested_build_jobs" =~ ^[1-9][0-9]*$ ]] ||
        fail "OVERTE_MACOS_BUILD_JOBS must be a positive integer"
    if [[ "$qt_source" == aqt ]]; then
        command -v aqt >/dev/null || fail "aqtinstall is missing (install it in a Python virtual environment)"
    fi
    note "Xcode: $(xcodebuild -version | tr '\n' ' ')"
    note "host: $(uname -m); target: $architecture; configuration: $build_type"
    note "Qt source: $qt_source; deployment target: ${MACOSX_DEPLOYMENT_TARGET:-11.0}; tests: $build_tests; jobs: $(effective_build_jobs)"
}

ensure_conan_profile() {
    conan profile path default >/dev/null 2>&1 || conan profile detect --name default
}

configure_remotes() {
    conan remote add overte https://artifactory.overte.org/artifactory/api/conan/overte --force
    conan remote update conancenter --url https://artifactory.overte.org/artifactory/api/conan/conan-center
}

conan_architecture() { [[ "$architecture" == arm64 ]] && echo armv8 || echo x86_64; }

prepare_dependencies() {
    doctor
    ensure_conan_profile
    configure_remotes
    conan export "$source_root/macos/conan/libnode" --user overte --channel macos
    if [[ "$qt_source" == aqt ]]; then
        # The published aqt recipe selects a Windows archive on macOS and does
        # not preserve the installer's executable bit. Export our macOS-only
        # repair under the same reference before resolving the graph.
        conan export "$source_root/macos/conan/qt-aqt" --user overte --channel aqt
    fi
}

deps_qt() {
    prepare_dependencies
    if [[ "$qt_source" != aqt ]]; then
        note "Qt preflight stage is only required for the aqt dependency"
        return
    fi
    mkdir -p "$build_dir/conan-stage-qt"
    local args=(-s "arch=$(conan_architecture)" -s compiler.cppstd=20
        -s "build_type=$build_type" -b missing)
    conan install --requires=qt/5.15.2@overte/aqt \
        -o 'qt/*:modules=qtwebengine' "${args[@]}" \
        -c "tools.build:jobs=$(effective_build_jobs)" \
        -of "$build_dir/conan-stage-qt"
}

deps_libnode() {
    prepare_dependencies
    mkdir -p "$build_dir/conan-stage-libnode"
    local args=(-s "arch=$(conan_architecture)" -s compiler.cppstd=20
        -s "build_type=$build_type" -b missing)
    conan install --requires=libnode/22.22.3@overte/macos \
        "${args[@]}" -c "tools.build:jobs=$(effective_build_jobs)" \
        -of "$build_dir/conan-stage-libnode"
}

deps() {
    prepare_dependencies
    mkdir -p "$build_dir"
    local args=("$source_root" -s "arch=$(conan_architecture)" -s compiler.cppstd=20
        -s "build_type=$build_type" -o "Overte/*:qt_source=$qt_source"
        -c "tools.build:jobs=$(effective_build_jobs)" -b missing -of "$build_dir")
    # Some legacy recipes only expose OpenSSL correctly on the second graph resolution.
    conan install "${args[@]}"
    conan install "${args[@]}"
}

configure() {
    doctor
    local skip_configure="${OVERTE_MACOS_SKIP_CONFIGURE:-OFF}"
    case "$skip_configure" in ON|OFF) ;; *) fail "OVERTE_MACOS_SKIP_CONFIGURE must be ON or OFF" ;; esac
    local cache_file="$build_dir/CMakeCache.txt"
    local ninja_file="$build_dir/build.ninja"
    local exact_key_file="$build_dir/.overte-macos-complete-key"
    local expected_exact_key="${OVERTE_MACOS_EXPECTED_BUILD_TREE_KEY:-}"
    cache_value() {
        local key="$1"
        sed -n "s/^${key}:[^=]*=//p" "$cache_file" | tail -n 1
    }
    if [[ "$skip_configure" == ON && -n "$expected_exact_key" ]] &&
       [[ -s "$exact_key_file" && "$(<"$exact_key_file")" == "$expected_exact_key" ]] &&
       [[ -s "$cache_file" && -s "$ninja_file" ]] &&
       [[ "$(cache_value CMAKE_HOME_DIRECTORY)" == "$source_root" ]] &&
       [[ "$(cache_value CMAKE_GENERATOR)" == Ninja ]] &&
       [[ "$(cache_value CMAKE_BUILD_TYPE)" == "$build_type" ]] &&
       [[ "$(cache_value CMAKE_OSX_ARCHITECTURES)" == "$architecture" ]] &&
       [[ "$(cache_value CMAKE_OSX_DEPLOYMENT_TARGET)" == "${MACOSX_DEPLOYMENT_TARGET:-11.0}" ]] &&
       [[ "$(cache_value OVERTE_BUILD_TESTS)" == "$build_tests" ]] &&
       [[ "$(cache_value OVERTE_RELEASE_TYPE)" == DEV ]] &&
       [[ "$(cache_value OVERTE_RENDERING_BACKEND)" == OpenGL ]]; then
        note "reusing exact verified CMake/Ninja graph"
        return
    fi
    if [[ "$skip_configure" == ON ]]; then
        local failed_invariants=()
        [[ -n "$expected_exact_key" ]] || failed_invariants+=(expected-key)
        [[ -s "$exact_key_file" ]] || failed_invariants+=(complete-key-file)
        [[ -s "$exact_key_file" && "$(<"$exact_key_file")" == "$expected_exact_key" ]] ||
            failed_invariants+=(complete-key-match)
        [[ -s "$cache_file" ]] || failed_invariants+=(cmake-cache)
        [[ -s "$ninja_file" ]] || failed_invariants+=(ninja-graph)
        if [[ -s "$cache_file" ]]; then
            [[ "$(cache_value CMAKE_HOME_DIRECTORY)" == "$source_root" ]] || failed_invariants+=(source-root)
            [[ "$(cache_value CMAKE_GENERATOR)" == Ninja ]] || failed_invariants+=(generator)
            [[ "$(cache_value CMAKE_BUILD_TYPE)" == "$build_type" ]] || failed_invariants+=(build-type)
            [[ "$(cache_value CMAKE_OSX_ARCHITECTURES)" == "$architecture" ]] || failed_invariants+=(architecture)
            [[ "$(cache_value CMAKE_OSX_DEPLOYMENT_TARGET)" == "${MACOSX_DEPLOYMENT_TARGET:-11.0}" ]] ||
                failed_invariants+=(deployment-target)
            [[ "$(cache_value OVERTE_BUILD_TESTS)" == "$build_tests" ]] || failed_invariants+=(tests)
            [[ "$(cache_value OVERTE_RELEASE_TYPE)" == DEV ]] || failed_invariants+=(release-type)
            [[ "$(cache_value OVERTE_RENDERING_BACKEND)" == OpenGL ]] || failed_invariants+=(rendering-backend)
        fi
        note "exact graph reuse was requested but cache invariants failed; configuring safely"
        note "failed exact graph invariants: ${failed_invariants[*]}"
    fi
    local preset="conan-$(printf '%s' "$build_type" | tr '[:upper:]' '[:lower:]')"
    local compiler_watchdog="$source_root/macos/ci/compiler-watchdog.py"
    local launcher_args=()
    if [[ -x "$compiler_watchdog" ]]; then
        launcher_args=(
            -D "CMAKE_C_COMPILER_LAUNCHER=$compiler_watchdog;--"
            -D "CMAKE_CXX_COMPILER_LAUNCHER=$compiler_watchdog;--"
            -D "CMAKE_OBJC_COMPILER_LAUNCHER=$compiler_watchdog;--"
            -D "CMAKE_OBJCXX_COMPILER_LAUNCHER=$compiler_watchdog;--"
        )
    fi
    cmake --preset "$preset" -G Ninja \
        -DOVERTE_RENDERING_BACKEND=OpenGL -DOVERTE_BUILD_CLIENT=ON \
        -DOVERTE_BUILD_SERVER=OFF -DOVERTE_BUILD_TOOLS=OFF \
        -DOVERTE_BUILD_TESTS="$build_tests" -DOVERTE_BUILD_INSTALLER=OFF \
        -DOVERTE_RELEASE_TYPE=DEV -DCMAKE_OSX_ARCHITECTURES="$architecture" \
        -DCMAKE_OSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-11.0}" \
        "${launcher_args[@]}"
}

compile() {
    local diagnostics_dir="$build_dir/macos-build-diagnostics"
    mkdir -p "$diagnostics_dir"
    local preset="conan-$(printf '%s' "$build_type" | tr '[:upper:]' '[:lower:]')"
    python3 "$source_root/macos/tools/run-build-with-progress.py" \
        --log "$diagnostics_dir/build.log" \
        --result "$diagnostics_dir/build-result.json" \
        --live-log "$diagnostics_dir/compiler-watchdog.jsonl" \
        --compiler-diagnostics-dir "$diagnostics_dir/compiler-stalls" -- \
        cmake --build --preset "$preset" --target Overte \
        --parallel "$(effective_build_jobs)"
    find "$build_dir" -type d -name Overte.app -print -quit
}

build() {
    note "phase=configure progress=0/100"
    if [[ "${GITHUB_ACTIONS:-false}" == true ]]; then
        echo "::notice title=macOS build progress::phase=configure progress=0/100"
    fi
    configure
    note "phase=configure progress=100/100"
    if [[ "${GITHUB_ACTIONS:-false}" == true ]]; then
        echo "::notice title=macOS build progress::phase=configure progress=100/100"
    fi
    compile
}

case "${1:-}" in
    doctor) doctor ;;
    prepare) prepare_dependencies ;;
    deps-qt) deps_qt ;;
    deps-libnode) deps_libnode ;;
    deps) deps ;;
    configure) configure ;;
    compile) compile ;;
    build) build ;;
    all) deps_qt; deps_libnode; deps; build ;;
    *) echo "Usage: macos/build-macos.sh doctor|prepare|deps-qt|deps-libnode|deps|configure|compile|build|all" >&2; exit 2 ;;
esac
