#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../.." && pwd)"

# shellcheck disable=SC1091
source "$repo_root/ios/versions.env"

readonly qt_version="${OVERTE_IOS_QT_VERSION:?OVERTE_IOS_QT_VERSION is not set}"
readonly qt_compact="${qt_version//./}"
readonly host_package="qt.qt6.${qt_compact}.clang_64"
readonly source_archive="qt-everywhere-src-${qt_version}.tar.xz"
readonly source_url="https://download.qt.io/official_releases/qt/6.11/${qt_version}/single/${source_archive}"
readonly source_sha256="252acef8c5ae68074d91cadba2ee4a83465051bbb970dd26e8f0daa0f3904e03"
readonly required_modules="${OVERTE_IOS_QT_REQUIRED_MODULES:-Core Gui Network Qml Quick Multimedia Svg WebChannel WebSockets WebView Core5Compat ShaderTools}"

die() {
    echo "error: $*" >&2
    exit 1
}

read_qt_version() {
    local root="$1"
    local cmake_dir="$root/lib/cmake/Qt6"
    local config version found="" saw_file=0

    # Qt's installed Qt6ConfigVersion.cmake is a dispatcher. Source-built Qt 6
    # stores the literal package version in Qt6ConfigVersionImpl.cmake, while
    # some packaged layouts still put it directly in Qt6ConfigVersion.cmake.
    for config in "$cmake_dir/Qt6ConfigVersionImpl.cmake" "$cmake_dir/Qt6ConfigVersion.cmake"; do
        [[ -f "$config" ]] || continue
        saw_file=1
        version="$(sed -nE 's/^[[:space:]]*set\(PACKAGE_VERSION[[:space:]]+"?([^" )]+)"?\).*/\1/p' "$config" | head -n 1)"
        [[ -n "$version" ]] || continue
        if [[ -n "$found" && "$found" != "$version" ]]; then
            die "conflicting Qt versions in $cmake_dir: $found and $version"
        fi
        found="$version"
    done

    ((saw_file)) || die "missing Qt version metadata in: $cmake_dir"
    printf '%s\n' "$found"
}

validate_root() {
    local kind="$1"
    local root="$2"
    local actual_version

    [[ -d "$root" ]] || die "$kind Qt root does not exist: $root"
    actual_version="$(read_qt_version "$root")"
    [[ -n "$actual_version" ]] || die "could not read $kind Qt version from $root"
    [[ "$actual_version" == "$qt_version" ]] ||
        die "$kind Qt is $actual_version; exactly $qt_version is required"
}

resolve_host_tool() {
    local host_root="$1"
    local tool="$2"
    local candidate

    # Source-built Qt 6 installs build helpers such as moc, rcc, and
    # qmlcachegen in libexec. Qt binary distributions may expose the same
    # tools from bin, while user-facing tools such as qsb normally live there.
    for candidate in "$host_root/bin/$tool" "$host_root/libexec/$tool"; do
        if [[ -x "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    die "host Qt tool is missing or not executable: $tool (checked $host_root/bin and $host_root/libexec)"
}

validate_target() {
    local target_root="$1"
    local module

    validate_root target "$target_root"
    [[ -x "$target_root/bin/qt-cmake" ]] || die "missing executable: $target_root/bin/qt-cmake"
    [[ -f "$target_root/lib/cmake/Qt6/qt.toolchain.cmake" ]] ||
        die "missing iOS Qt toolchain: $target_root/lib/cmake/Qt6/qt.toolchain.cmake"
    grep -Eq 'set\(QT_OSX_ARCHITECTURES "arm64"' \
        "$target_root/lib/cmake/Qt6/qt.toolchain.cmake" ||
        die "target Qt toolchain is not restricted to arm64: $target_root"
    [[ -f "$target_root/mkspecs/macx-ios-clang/qmake.conf" ]] ||
        die "target Qt does not contain the macx-ios-clang device specification: $target_root"
    compgen -G "$target_root/lib/cmake/Qt6Gui/Qt6QIOSIntegrationPlugin*.cmake" >/dev/null ||
        die "target Qt does not contain the iOS QPA integration metadata: $target_root"

    for module in $required_modules; do
        [[ -f "$target_root/lib/cmake/Qt6${module}/Qt6${module}Config.cmake" ]] ||
            die "target Qt module is missing: Qt6$module"
    done
}

validate_host() {
    local host_root="$1"
    local tool

    validate_root host "$host_root"
    for tool in moc rcc qmlcachegen qsb; do
        resolve_host_tool "$host_root" "$tool" >/dev/null
    done
}

validate() {
    local target_root="${OVERTE_IOS_QT_ROOT:-${1:-}}"
    local host_root="${OVERTE_IOS_QT_HOST_ROOT:-${2:-}}"

    [[ -n "$target_root" ]] || die "set OVERTE_IOS_QT_ROOT or pass the iOS Qt root as argument"
    [[ -n "$host_root" ]] || die "set OVERTE_IOS_QT_HOST_ROOT or pass the macOS Qt root as second argument"
    validate_target "$target_root"
    validate_host "$host_root"

    printf 'Qt iOS toolchain validated\n'
    printf '  version: %s\n  target:  %s\n  host:    %s\n' "$qt_version" "$target_root" "$host_root"
}

installer_command() {
    local installer="${1:-}"
    local install_root="${2:-${OVERTE_IOS_QT_INSTALL_ROOT:-}}"
    [[ -n "$installer" ]] || die "usage: $0 installer-command INSTALLER INSTALL_ROOT"
    [[ -n "$install_root" ]] || die "pass INSTALL_ROOT or set OVERTE_IOS_QT_INSTALL_ROOT"
    [[ -x "$installer" ]] || die "installer is not executable: $installer"

    printf '%q --root %q install %q\n' \
        "$installer" "$install_root" "$host_package"
    cat <<'EOF'

Run the printed command interactively. It intentionally does not supply Qt
credentials, --accept-licenses, --default-answer, or --confirm-command. Review
the displayed license and package information yourself before continuing.
EOF
}

verify_source() {
    local archive="${1:-}"
    local actual
    [[ -f "$archive" ]] || die "usage: $0 verify-source SOURCE_ARCHIVE"
    if command -v shasum >/dev/null 2>&1; then
        actual="$(shasum -a 256 "$archive" | awk '{print $1}')"
    elif command -v sha256sum >/dev/null 2>&1; then
        actual="$(sha256sum "$archive" | awk '{print $1}')"
    else
        die "neither shasum nor sha256sum is available"
    fi
    [[ "$actual" == "$source_sha256" ]] || die "Qt source SHA-256 mismatch: $actual"
    printf 'Qt source archive verified: %s\n' "$archive"
}

manifest() {
    printf 'QT_VERSION=%s\nQT_HOST_PACKAGE=%s\nQT_IOS_DISTRIBUTION=%s\nQT_SOURCE_URL=%s\nQT_SOURCE_SHA256=%s\n' \
        "$qt_version" "$host_package" "source-or-entitled-cache" "$source_url" "$source_sha256"
}

case "${1:-}" in
    validate-host)
        shift
        host_root="${OVERTE_IOS_QT_HOST_ROOT:-${1:-}}"
        [[ -n "$host_root" ]] || die "set OVERTE_IOS_QT_HOST_ROOT or pass the macOS Qt root"
        validate_host "$host_root"
        printf 'Qt host tools validated: %s\n' "$host_root"
        ;;
    validate-target)
        shift
        target_root="${OVERTE_IOS_QT_ROOT:-${1:-}}"
        [[ -n "$target_root" ]] || die "set OVERTE_IOS_QT_ROOT or pass the iOS Qt root"
        validate_target "$target_root"
        printf 'Qt iOS target validated: %s\n' "$target_root"
        ;;
    validate)
        shift
        validate "$@"
        ;;
    installer-command)
        shift
        installer_command "$@"
        ;;
    manifest)
        manifest
        ;;
    verify-source)
        shift
        verify_source "$@"
        ;;
    *)
        die "usage: $0 {manifest|installer-command INSTALLER INSTALL_ROOT|verify-source ARCHIVE|validate-host [HOST_ROOT]|validate-target [IOS_ROOT]|validate [IOS_ROOT [HOST_ROOT]]}"
        ;;
esac
