#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly source_root="$(cd -- "$script_dir/.." && pwd)"
readonly versions_file="$script_dir/versions.env"

fail() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

note() {
    printf '%s\n' "$*"
}

usage() {
    cat <<'EOF'
Usage: ios/build-ios.sh COMMAND [OPTIONS]

Commands:
  doctor                         Validate the macOS, Xcode, CMake and Conan host.
  bootstrap                      Create the local Python tool environment.
  deps --platform TARGET        Resolve the staged native dependency graph.
  configure --platform TARGET   Generate the Xcode project (simulator or device).
  build --platform TARGET       Configure and build the bootstrap application.
  test [--platform TARGET]      Run host contracts, optionally build for TARGET.
  package --platform TARGET     Produce an unsigned simulator archive or device app.
  clean --platform TARGET       Print the build directory; use --confirm to remove it.

Options:
  --platform simulator|device   Target platform. Defaults to simulator.
  --configuration NAME          Xcode configuration. Defaults to Debug.
  --build-dir PATH              Override the target build directory.
  --bundle-id IDENTIFIER        Override org.overte.interface.dev.
  --development-team TEAM       Enable device signing with this Apple team ID.
  --require-qt                  Make doctor fail unless Qt 6 for iOS is configured.
  --require-v8                  Make doctor validate the static iOS V8/libnode package.
  --graphics-toolchain          Include Vulkan and host shader tools in deps.
  --require-moltenvk            Make doctor validate the MoltenVK XCFramework.
  --confirm                     Confirm clean removal of the resolved build directory.
  -h, --help                    Show this help.

Signing is disabled unless --development-team is supplied for a device build.
EOF
}

[[ -f "$versions_file" ]] || fail "missing version contract: $versions_file"
# shellcheck disable=SC1090
source "$versions_file"

command_name="${1:-}"
[[ -n "$command_name" ]] || {
    usage
    exit 2
}
shift

platform="simulator"
configuration="Debug"
build_dir=""
bundle_id="org.overte.interface.dev"
development_team=""
confirm_clean=0
require_qt=0
require_v8=0
with_graphics_toolchain=False
require_moltenvk=0

while (($#)); do
    case "$1" in
        --platform)
            (($# >= 2)) || fail "--platform requires a value"
            platform="$2"
            shift 2
            ;;
        --configuration)
            (($# >= 2)) || fail "--configuration requires a value"
            configuration="$2"
            shift 2
            ;;
        --build-dir)
            (($# >= 2)) || fail "--build-dir requires a value"
            build_dir="$2"
            shift 2
            ;;
        --bundle-id)
            (($# >= 2)) || fail "--bundle-id requires a value"
            bundle_id="$2"
            shift 2
            ;;
        --development-team)
            (($# >= 2)) || fail "--development-team requires a value"
            development_team="$2"
            shift 2
            ;;
        --confirm)
            confirm_clean=1
            shift
            ;;
        --require-qt)
            require_qt=1
            shift
            ;;
        --require-v8)
            require_v8=1
            shift
            ;;
        --graphics-toolchain)
            with_graphics_toolchain=True
            shift
            ;;
        --require-moltenvk)
            require_moltenvk=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "unknown option: $1"
            ;;
    esac
done

case "$platform" in
    simulator)
        sdk_name="iphonesimulator"
        conan_profile="$script_dir/conan/profiles/ios-simulator-arm64"
        ;;
    device)
        sdk_name="iphoneos"
        conan_profile="$script_dir/conan/profiles/ios-arm64"
        ;;
    *)
        fail "unsupported platform '$platform'; use simulator or device"
        ;;
esac

[[ "$configuration" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] \
    || fail "invalid Xcode configuration name: $configuration"
[[ "$bundle_id" =~ ^[A-Za-z0-9][A-Za-z0-9-]*(\.[A-Za-z0-9][A-Za-z0-9-]*)+$ ]] \
    || fail "invalid bundle identifier: $bundle_id"
if [[ -n "$development_team" && ! "$development_team" =~ ^[A-Z0-9]{10}$ ]]; then
    fail "Apple development team IDs must contain exactly 10 uppercase letters or digits"
fi

if [[ -z "$build_dir" ]]; then
    build_dir="$source_root/build-ios/$platform"
elif [[ "$build_dir" != /* ]]; then
    build_dir="$source_root/$build_dir"
fi

version_at_least() {
    local actual="$1"
    local required="$2"
    python3 "$script_dir/tools/version-at-least.py" "$actual" "$required"
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

require_macos() {
    [[ "$(uname -s)" == "Darwin" ]] || fail "iOS builds require macOS with Xcode"
}

run_doctor() {
    require_macos
    require_command xcodebuild
    require_command xcrun
    require_command cmake
    require_command python3

    local xcode_version sdk_version cmake_version conan_version python_version
    xcode_version="$(xcodebuild -version | sed -n '1s/^Xcode //p')"
    [[ -n "$xcode_version" ]] || fail "could not determine the Xcode version"
    version_at_least "$xcode_version" "$OVERTE_IOS_REQUIRED_XCODE_MAJOR" \
        || fail "Xcode $OVERTE_IOS_REQUIRED_XCODE_MAJOR or newer is required; found $xcode_version"

    sdk_version="$(xcrun --sdk "$sdk_name" --show-sdk-version)"
    version_at_least "$sdk_version" "$OVERTE_IOS_REQUIRED_SDK_MAJOR" \
        || fail "iOS SDK $OVERTE_IOS_REQUIRED_SDK_MAJOR or newer is required; found $sdk_version"

    cmake_version="$(cmake --version | sed -n '1s/^cmake version //p')"
    version_at_least "$cmake_version" "$OVERTE_IOS_CMAKE_MIN_VERSION" \
        || fail "CMake $OVERTE_IOS_CMAKE_MIN_VERSION or newer is required; found $cmake_version"

    python_version="$(python3 -c 'import platform; print(platform.python_version())')"
    version_at_least "$python_version" "$OVERTE_IOS_PYTHON_MIN_VERSION" \
        || fail "Python $OVERTE_IOS_PYTHON_MIN_VERSION or newer is required; found $python_version"

    if command -v conan >/dev/null 2>&1; then
        conan_version="$(conan --version | awk '{print $3}')"
        [[ "$conan_version" == "$OVERTE_IOS_CONAN_VERSION" ]] \
            || fail "Conan $OVERTE_IOS_CONAN_VERSION is required for the audited graph; found $conan_version"
    else
        conan_version="not installed (run bootstrap before dependency resolution)"
    fi

    note "Xcode: $xcode_version"
    note "$sdk_name SDK: $sdk_version"
    note "CMake: $cmake_version"
    note "Python: $python_version"
    note "Conan: $conan_version"
    note "Conan host profile: $conan_profile"

    local qt_root="${OVERTE_IOS_QT_ROOT:-}"
    if [[ -n "$qt_root" ]]; then
        [[ -f "$qt_root/lib/cmake/Qt6/Qt6Config.cmake" ]] \
            || fail "OVERTE_IOS_QT_ROOT does not contain lib/cmake/Qt6/Qt6Config.cmake"
        local qt_version_file="$qt_root/lib/cmake/Qt6/Qt6ConfigVersionImpl.cmake"
        [[ -f "$qt_version_file" ]] \
            || fail "OVERTE_IOS_QT_ROOT does not contain Qt6ConfigVersionImpl.cmake"
        [[ -x "$qt_root/bin/qt-cmake" ]] \
            || fail "OVERTE_IOS_QT_ROOT does not contain bin/qt-cmake"
        local qt_version
        qt_version="$(sed -n 's/^set(PACKAGE_VERSION "\([0-9.]*\)")$/\1/p' "$qt_version_file" | head -n 1)"
        [[ -n "$qt_version" ]] || fail "could not determine Qt version below OVERTE_IOS_QT_ROOT"
        version_at_least "$qt_version" "$OVERTE_IOS_QT_MIN_VERSION" \
            || fail "Qt $OVERTE_IOS_QT_MIN_VERSION or newer is required; found $qt_version"
        note "Qt for iOS: $qt_root ($qt_version)"
    elif ((require_qt)); then
        fail "set OVERTE_IOS_QT_ROOT to a Qt 6 iOS installation"
    else
        note "Qt for iOS: not configured (native bootstrap only)"
    fi

    local v8_root="${OVERTE_IOS_V8_ROOT:-}"
    if [[ -n "$v8_root" ]]; then
        [[ -f "$v8_root/include/node/v8.h" ]] \
            || fail "OVERTE_IOS_V8_ROOT does not contain include/node/v8.h"
        local v8_archive=""
        for candidate in "$v8_root/lib/libnode.a" "$v8_root/lib/libv8_monolith.a"; do
            if [[ -f "$candidate" ]]; then
                v8_archive="$candidate"
                break
            fi
        done
        [[ -n "$v8_archive" ]] \
            || fail "OVERTE_IOS_V8_ROOT does not contain a static libnode.a or libv8_monolith.a"
        require_command lipo
        lipo "$v8_archive" -verify_arch arm64 >/dev/null \
            || fail "iOS V8 archive does not contain arm64: $v8_archive"
        note "Static non-JIT V8: $v8_archive (arm64)"
    elif ((require_v8)); then
        fail "set OVERTE_IOS_V8_ROOT to an audited static non-JIT iOS package"
    else
        note "Static non-JIT V8: not configured (scripting integration disabled)"
    fi

    local moltenvk_root="${OVERTE_IOS_MOLTENVK_ROOT:-}"
    if [[ -n "$moltenvk_root" ]]; then
        local moltenvk_slice="ios-arm64"
        [[ "$platform" == "simulator" ]] && moltenvk_slice="ios-arm64_x86_64-simulator"
        [[ -f "$moltenvk_root/MoltenVK/include/vulkan/vulkan.h" ]] \
            || fail "MoltenVK headers not found below OVERTE_IOS_MOLTENVK_ROOT"
        [[ -f "$moltenvk_root/MoltenVK/MoltenVK.xcframework/$moltenvk_slice/libMoltenVK.a" ]] \
            || fail "MoltenVK static slice not found: $moltenvk_slice"
        require_command lipo
        lipo "$moltenvk_root/MoltenVK/MoltenVK.xcframework/$moltenvk_slice/libMoltenVK.a" \
            -verify_arch arm64 >/dev/null \
            || fail "MoltenVK static slice does not contain arm64: $moltenvk_slice"
        note "MoltenVK: $moltenvk_root ($moltenvk_slice)"
    elif ((require_moltenvk)); then
        fail "set OVERTE_IOS_MOLTENVK_ROOT to an unpacked MoltenVK distribution"
    else
        note "MoltenVK: not configured (native Metal bootstrap only)"
    fi
    note "iOS build environment is ready for the $platform bootstrap target."
}

run_bootstrap() {
    require_macos
    require_command python3
    require_command cmake
    require_command xcodebuild
    require_command xcrun

    local python_version
    python_version="$(python3 -c 'import platform; print(platform.python_version())')"
    version_at_least "$python_version" "$OVERTE_IOS_PYTHON_MIN_VERSION" \
        || fail "Python $OVERTE_IOS_PYTHON_MIN_VERSION or newer is required; found $python_version"

    local venv_dir="$source_root/build-ios/tooling-venv"
    python3 -m venv "$venv_dir"
    "$venv_dir/bin/python" -m pip install --upgrade pip
    "$venv_dir/bin/python" -m pip install "conan==${OVERTE_IOS_CONAN_VERSION}"
    "$venv_dir/bin/python" -m pip freeze --all > "$venv_dir/tooling-versions.txt"
    note "Tool environment created at $venv_dir"
    note "Resolved Python tooling recorded at $venv_dir/tooling-versions.txt"
    note "Activate it with: source $venv_dir/bin/activate"
}

resolve_dependencies() {
    run_doctor
    require_command conan
    local sdk_path conan_output="$build_dir/conan"
    sdk_path="$(xcrun --sdk "$sdk_name" --show-sdk-path)"
    if [[ "$platform" == "simulator" ]]; then
        export OVERTE_IOS_SIMULATOR_SDK_PATH="$sdk_path"
    else
        export OVERTE_IOS_DEVICE_SDK_PATH="$sdk_path"
    fi
    mkdir -p "$conan_output"
    conan install "$script_dir" \
        --profile:host="$conan_profile" \
        --profile:build=default \
        --build=missing \
        --options="overte-ios-dependencies/*:with_graphics_toolchain=$with_graphics_toolchain" \
        --output-folder="$conan_output" \
        --format=json > "$conan_output/graph.json"
    python3 "$script_dir/tools/audit-conan-graph.py" "$conan_output/graph.json"
    python3 "$script_dir/tools/generate-sbom.py" \
        "$conan_output/graph.json" "$script_dir/dependencies.json" "$conan_output/sbom.cdx.json"
    note "Resolved staged dependency graph at $conan_output"
    note "Generated dependency and compliance inventory at $conan_output/sbom.cdx.json"
}

configure_project() {
    run_doctor
    local sdk_path signing=OFF
    sdk_path="$(xcrun --sdk "$sdk_name" --show-sdk-path)"
    if [[ -n "$development_team" ]]; then
        [[ "$platform" == "device" ]] \
            || fail "--development-team is only valid with --platform device"
        signing=ON
    fi

    cmake -S "$source_root" -B "$build_dir" -G Xcode \
        -DCMAKE_SYSTEM_NAME=iOS \
        -DCMAKE_OSX_ARCHITECTURES=arm64 \
        -DCMAKE_OSX_DEPLOYMENT_TARGET="$OVERTE_IOS_MIN_VERSION" \
        -DCMAKE_OSX_SYSROOT="$sdk_path" \
        -DOVERTE_IOS_BUNDLE_IDENTIFIER="$bundle_id" \
        -DOVERTE_IOS_DEVELOPMENT_TEAM="$development_team" \
        -DOVERTE_IOS_ENABLE_SIGNING="$signing" \
        -DOVERTE_IOS_BOOTSTRAP_ONLY=ON
}

build_project() {
    configure_project
    cmake --build "$build_dir" --config "$configuration" --target OverteIOSBootstrap
}

run_tests() {
    "$script_dir/tests/run-tests.sh"
    if [[ "$platform" == "simulator" || "$platform" == "device" ]]; then
        if [[ "$(uname -s)" == "Darwin" ]]; then
            build_project
        else
            note "Skipping Xcode build tier on non-macOS host."
        fi
    fi
}

run_package() {
    build_project
    local app_path="$build_dir/ios/$configuration-iphoneos/OverteIOSBootstrap.app"
    if [[ "$platform" == "simulator" ]]; then
        app_path="$build_dir/ios/$configuration-iphonesimulator/OverteIOSBootstrap.app"
    fi
    [[ -d "$app_path" ]] || fail "built application not found: $app_path"

    local artifact_dir="$source_root/build-ios/artifacts"
    mkdir -p "$artifact_dir"
    if [[ "$platform" == "simulator" ]]; then
        local archive="$artifact_dir/OverteIOSBootstrap-${configuration}-simulator.zip"
        ditto -c -k --sequesterRsrc --keepParent "$app_path" "$archive"
        local archive_sha source_revision manifest
        archive_sha="$(shasum -a 256 "$archive" | awk '{print $1}')"
        source_revision="$(git -C "$source_root" rev-parse HEAD)"
        manifest="$artifact_dir/OverteIOSBootstrap-${configuration}-simulator.json"
        python3 - "$manifest" "$archive" "$archive_sha" "$source_revision" \
            "$configuration" "$(xcodebuild -version | tr '\n' ' ')" \
            "$(xcrun --sdk iphonesimulator --show-sdk-version)" <<'PY'
import json
import pathlib
import sys

output, archive, digest, revision, configuration, xcode, sdk = sys.argv[1:]
payload = {
    "schemaVersion": 1,
    "artifact": pathlib.Path(archive).name,
    "sha256": digest,
    "sourceRevision": revision,
    "platform": "iphonesimulator",
    "architecture": "arm64",
    "configuration": configuration,
    "xcode": xcode.strip(),
    "sdk": sdk,
    "signed": False,
}
pathlib.Path(output).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
        note "Created unsigned simulator artifact: $archive"
        note "Created artifact manifest: $manifest"
    else
        note "Device application ready at: $app_path"
    fi
}

run_clean() {
    case "$build_dir" in
        "$source_root"/build-ios/simulator|"$source_root"/build-ios/device|"$source_root"/build-ios/custom-*) ;;
        *) fail "refusing to clean unrecognized directory: $build_dir" ;;
    esac
    if ((confirm_clean == 0)); then
        note "Resolved build directory: $build_dir"
        note "Run again with --confirm to remove it."
        return
    fi
    [[ -e "$build_dir" ]] || {
        note "Build directory does not exist: $build_dir"
        return
    }
    rm -rf -- "$build_dir"
    note "Removed build directory: $build_dir"
}

case "$command_name" in
    doctor) run_doctor ;;
    bootstrap) run_bootstrap ;;
    deps) resolve_dependencies ;;
    configure) configure_project ;;
    build) build_project ;;
    test) run_tests ;;
    package) run_package ;;
    clean) run_clean ;;
    help|-h|--help) usage ;;
    *)
        usage >&2
        fail "unknown command: $command_name"
        ;;
esac
