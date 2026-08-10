#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
android_root="$(cd -- "$script_dir/../.." && pwd)"
source "$android_root/common/scripts/with-temporary-git-patch.sh"
conan_home="${CONAN_HOME:-${HOME}/.conan2}"
jobs="${PICO_BUILD_JOBS:-$(nproc)}"
command_name="${1:-all}"
command_option="${2:-}"
prebuilt_tag="pico4-deps-v1"
qt_reference='qt/5.15.18-2026.01.04@overte/stable#d59ba2a04fe9ede772b05b0bb0865eb0'
android_cmake_version="3.31.6"
android_tools_url="https://developer.android.com/studio"
android_repository_url="https://dl.google.com/android/repository/repository2-1.xml"
platform_tools_url="https://developer.android.com/tools/releases/platform-tools"
conan_install_url="https://docs.conan.io/2/installation.html"
overte_conan_url="https://artifactory.overte.org/artifactory/api/conan/overte"
cmake_install_url="https://cmake.org/download/"
ninja_install_url="https://github.com/ninja-build/ninja/releases"
git_install_url="https://git-scm.com/downloads"
python_install_url="https://www.python.org/downloads/"
perl_install_url="https://www.perl.org/get.html"
temurin_api_url="https://api.adoptium.net/v3/assets/latest/21/hotspot"

fail() {
    echo "error: $*" >&2
    exit 2
}

[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || fail "PICO_BUILD_JOBS must be a positive integer"

find_conan() {
    local candidate

    if [[ -n "${PICO_CONAN:-}" ]]; then
        if [[ -x "$PICO_CONAN" ]]; then
            printf '%s\n' "$PICO_CONAN"
            return 0
        fi
        command -v "$PICO_CONAN" 2>/dev/null && return 0
    fi

    command -v conan 2>/dev/null && return 0
    for candidate in \
        "${HOME}/.local/bin/conan" \
        "${PIPX_HOME:-${HOME}/.local/share/pipx}/venvs/conan/bin/conan"; do
        if [[ -x "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

run_conan() {
    local conan_path
    conan_path="$(find_conan)" \
        || fail "Conan 2 was not found (install: $conan_install_url)"
    "$conan_path" "$@"
}

usage() {
    cat <<'EOF'
Usage: ./build-pico.sh [doctor|bootstrap|deps|prepare|build|install|all|deploy|setup] [option]

  doctor   Check the development environment and print installation help
  bootstrap [--check|--system-packages|--with-deps]
           Install as many missing build requirements as possible
  deps     Install dependencies; use --download for prebuilt Qt and Node
  prepare  Locate and stage the existing Conan/Qt dependencies
  build [--stacktrace]
           Build the Pico debug APK; optionally include Gradle failure details
  release [--stacktrace]
           Build a signed Pico release APK (requires protected Gradle properties)
  install  Install the existing APK on a connected Pico via ADB
  all      Prepare dependencies and build the APK (default)
  deploy   Prepare, build, and install the APK
  setup    Install dependencies, prepare them, and build the APK

Detected paths can be overridden with ANDROID_SDK_ROOT, JAVA_HOME,
PICO_QT_SOURCE_DIR, PICO_QT_BUILD_DIR, PICO_TBB_PACKAGE_DIR,
PICO_DRACO_PACKAGE_DIR, PICO_CONAN, and the PICO_* host-tool variables.
EOF
}

doctor() {
    local errors=0 warnings=0 command_path version sdk_path ndk_path adb_path
    local detected_java="" major="" free_kb

    doctor_ok() { printf '  [OK]   %s\n' "$*"; }
    doctor_warn() { printf '  [WARN] %s\n' "$*"; warnings=$((warnings + 1)); }
    doctor_error() { printf '  [MISS] %s\n' "$*"; errors=$((errors + 1)); }

    echo "Pico 4 build environment"
    echo
    echo "Command-line tools:"

    if command_path="$(find_conan)"; then
        version="$("$command_path" --version 2>/dev/null || true)"
        if [[ "$version" =~ Conan\ version\ 2\. ]]; then
            doctor_ok "$version ($command_path)"
            if "$command_path" profile path default >/dev/null 2>&1; then
                doctor_ok "Conan default profile"
            else
                doctor_error "the Conan default profile is missing"
                echo "           Create it with: $command_path profile detect --force"
            fi
        else
            doctor_error "Conan 2 is required; found: ${version:-unknown version}"
            echo "           Install: $conan_install_url"
        fi
    else
        doctor_error "Conan 2 is not installed or not in PATH"
        echo "           Install: $conan_install_url"
    fi

    local tool url
    for tool in git curl cmake ninja python3 perl; do
        case "$tool" in
            git) url="$git_install_url" ;;
            curl) url="https://curl.se/download.html" ;;
            cmake) url="$cmake_install_url" ;;
            ninja) url="$ninja_install_url" ;;
            python3) url="$python_install_url" ;;
            perl) url="$perl_install_url" ;;
        esac
        if command_path="$(command -v "$tool" 2>/dev/null)"; then
            doctor_ok "$tool ($command_path)"
        else
            doctor_error "$tool is not installed or not in PATH"
            echo "           Install: $url"
        fi
    done

    for tool in c++ file find make ar tar awk sha1sum sha256sum unzip flock; do
        if command_path="$(command -v "$tool" 2>/dev/null)"; then
            doctor_ok "$tool ($command_path)"
        else
            doctor_error "$tool is not installed or not in PATH"
            echo "           Install it with your operating system's development-tools package."
        fi
    done

    echo
    echo "Android toolchain:"
    sdk_path=""
    local candidate
    for candidate in "${ANDROID_SDK_ROOT:-}" "${ANDROID_HOME:-}" "${HOME}/Android/Sdk"; do
        if [[ -n "$candidate" && -d "$candidate" ]]; then
            sdk_path="$candidate"
            break
        fi
    done
    if [[ -z "$sdk_path" ]]; then
        doctor_error "Android SDK was not found"
        echo "           Install Android Studio or the command-line tools: $android_tools_url"
    else
        doctor_ok "Android SDK ($sdk_path)"
        if [[ -d "$sdk_path/platforms/android-36" ]]; then
            doctor_ok "Android SDK Platform 36"
        else
            doctor_error "Android SDK Platform 36 is missing"
            echo "           Install with SDK Manager: sdkmanager \"platforms;android-36\""
            echo "           Help: $android_tools_url"
        fi
        if [[ -d "$sdk_path/build-tools/36.0.0" ]]; then
            doctor_ok "Android SDK Build-Tools 36.0.0"
        else
            doctor_error "Android SDK Build-Tools 36.0.0 is missing"
            echo "           Install with SDK Manager: sdkmanager \"build-tools;36.0.0\""
            echo "           Help: $android_tools_url"
        fi

        if [[ -x "$sdk_path/cmake/$android_cmake_version/bin/cmake" ]]; then
            doctor_ok "Android SDK CMake $android_cmake_version"
        else
            doctor_error "Android SDK CMake $android_cmake_version is missing"
            echo "           Install with SDK Manager: sdkmanager \"cmake;$android_cmake_version\""
            echo "           Help: $android_tools_url"
        fi

        ndk_path="${ANDROID_NDK_HOME:-$sdk_path/ndk/27.3.13750724}"
        if [[ -d "$ndk_path" ]]; then
            doctor_ok "Android NDK 27.3.13750724 ($ndk_path)"
        else
            doctor_error "Android NDK 27.3.13750724 is missing"
            echo "           Install with SDK Manager: sdkmanager \"ndk;27.3.13750724\""
            echo "           Help: $android_tools_url"
        fi

        adb_path="${PICO_ADB:-$sdk_path/platform-tools/adb}"
        if [[ -x "$adb_path" ]]; then
            doctor_ok "Android Platform-Tools/ADB ($adb_path)"
        else
            doctor_error "Android Platform-Tools/ADB is missing"
            echo "           Install: $platform_tools_url"
        fi
    fi

    echo
    echo "Java and project files:"
    detected_java="$(find_compatible_jdk || true)"
    [[ -z "$detected_java" ]] || major="$(java_major "$detected_java")"
    if [[ -n "$detected_java" ]]; then
        doctor_ok "JDK $major ($detected_java)"
    else
        doctor_error "a JDK between versions 17 and 21 was not found"
        echo "           Android Studio includes a compatible JDK: $android_tools_url"
    fi

    if [[ -x "$android_root/common/gradlew" ]]; then
        doctor_ok "Gradle wrapper ($android_root/common/gradlew)"
    else
        doctor_error "the project Gradle wrapper is missing or not executable"
    fi

    free_kb=""
    if command -v awk >/dev/null 2>&1; then
        free_kb="$(df -Pk "$script_dir" | awk 'NR == 2 { print $4 }')"
    fi
    if [[ "$free_kb" =~ ^[0-9]+$ && "$free_kb" -lt 15728640 ]]; then
        doctor_warn "less than 15 GiB of free disk space is available"
    else
        doctor_ok "at least 15 GiB of free disk space"
    fi

    echo
    if [[ "$errors" -eq 0 ]]; then
        echo "Ready: all required build tools were found ($warnings warning(s))."
        echo "Next: ./build-pico.sh setup --download"
        return 0
    fi
    echo "Not ready: $errors required item(s) missing, $warnings warning(s)."
    return 2
}

run_as_root() {
    if [[ "$(id -u)" -eq 0 ]]; then
        "$@"
    elif command -v sudo >/dev/null; then
        sudo "$@"
    else
        fail "system packages are missing and sudo is unavailable"
    fi
}

install_system_packages() {
    local needs_packages=0 tool
    for tool in git curl cmake ninja python3 perl c++ file find make ar tar awk sha1sum sha256sum unzip flock; do
        command -v "$tool" >/dev/null 2>&1 || needs_packages=1
    done
    find_conan >/dev/null 2>&1 || command -v pipx >/dev/null 2>&1 || needs_packages=1

    if [[ "$needs_packages" -eq 0 ]]; then
        echo "System build tools are already installed"
        return
    fi

    echo "Installing missing system build tools (administrator access may be requested)"
    if command -v dnf >/dev/null; then
        run_as_root dnf install -y git curl cmake ninja-build python3 python3-pip \
            pipx perl-interpreter gcc-c++ file findutils make binutils tar gawk coreutils unzip util-linux
    elif command -v apt-get >/dev/null; then
        run_as_root apt-get update
        run_as_root apt-get install -y git curl cmake ninja-build python3 python3-pip \
            pipx perl g++ file findutils make binutils tar gawk coreutils unzip util-linux
    elif command -v pacman >/dev/null; then
        run_as_root pacman -Syu --needed --noconfirm git curl cmake ninja python \
            python-pipx perl gcc file findutils make binutils tar gawk coreutils unzip util-linux
    elif command -v zypper >/dev/null; then
        run_as_root zypper --non-interactive install git curl cmake ninja python3 \
            python3-pipx perl gcc-c++ file findutils make binutils tar gzip coreutils unzip util-linux
    else
        fail "unsupported package manager; install the items reported by ./build-pico.sh doctor"
    fi
}

install_android_command_line_tools() {
    local sdk_path="$1" metadata download_name checksum checksum_type
    local download_dir archive extracted_tools

    if [[ ! -t 0 ]]; then
        fail "Android command-line tools require interactive license acceptance (install: $android_tools_url)"
    fi
    echo
    echo "The Android command-line tools are subject to the Android SDK License Agreement:"
    echo "$android_tools_url"
    read -r -p "Have you read and accepted the Android SDK License Agreement? [y/N] " answer
    case "$answer" in
        y|Y|yes|YES) ;;
        *) fail "Android SDK license acceptance is required to install the command-line tools" ;;
    esac

    echo "Resolving the latest official Android command-line tools"
    metadata="$(curl --fail --location --retry 3 --silent --show-error \
        "$android_repository_url")"
    read -r download_name checksum checksum_type < <(python3 -c '
import sys, xml.etree.ElementTree as ET
root = ET.parse(sys.stdin).getroot()
for package in root.findall("remotePackage"):
    if package.get("path") != "cmdline-tools;latest":
        continue
    for archive in package.findall("./archives/archive"):
        if archive.findtext("host-os") == "linux":
            complete = archive.find("complete")
            checksum = complete.find("checksum")
            print(complete.findtext("url"), checksum.text, checksum.get("type", "sha1"))
            raise SystemExit
raise SystemExit("no Linux command-line tools found in the Android repository")
' <<< "$metadata")
    [[ -n "$download_name" && -n "$checksum" ]] \
        || fail "the Android repository returned incomplete command-line tools metadata"

    download_dir="$(mktemp -d)"
    archive="$download_dir/android-command-line-tools.zip"
    trap 'rm -rf -- "$download_dir"' RETURN
    echo "Downloading Android command-line tools"
    curl --fail --location --retry 3 --output "$archive" \
        "https://dl.google.com/android/repository/$download_name"
    case "$checksum_type" in
        sha1) echo "$checksum  $archive" | sha1sum --check --status ;;
        sha256) echo "$checksum  $archive" | sha256sum --check --status ;;
        *) fail "unsupported Android archive checksum: $checksum_type" ;;
    esac || fail "invalid checksum for downloaded Android command-line tools"

    unzip -q "$archive" -d "$download_dir/extracted"
    extracted_tools="$download_dir/extracted/cmdline-tools"
    [[ -x "$extracted_tools/bin/sdkmanager" ]] \
        || fail "the Android archive does not contain sdkmanager"
    install -d "$sdk_path/cmdline-tools"
    [[ ! -e "$sdk_path/cmdline-tools/latest" ]] \
        || fail "an incomplete command-line tools installation already exists: $sdk_path/cmdline-tools/latest"
    mv "$extracted_tools" "$sdk_path/cmdline-tools/latest"
    rm -rf -- "$download_dir"
    trap - RETURN
    echo "Installed Android command-line tools in $sdk_path/cmdline-tools/latest"
}

install_compatible_jdk() {
    local architecture metadata download_url checksum download_dir archive
    local install_parent="$script_dir/pico-host-tools"
    local install_dir="$install_parent/jdk-21"
    local temporary_install

    if [[ -n "$(find_compatible_jdk || true)" ]]; then
        echo "A compatible JDK is already installed"
        return
    fi
    command -v curl >/dev/null || fail "curl is required to download JDK 21"
    command -v python3 >/dev/null || fail "Python is required to resolve the JDK 21 download"

    case "$(uname -m)" in
        x86_64) architecture="x64" ;;
        aarch64|arm64) architecture="aarch64" ;;
        *) fail "automatic JDK installation is unsupported on $(uname -m)" ;;
    esac

    echo "Resolving the latest Eclipse Temurin 21 JDK"
    metadata="$(curl --fail --location --retry 3 --silent --show-error \
        "${temurin_api_url}?architecture=${architecture}&image_type=jdk&os=linux&vendor=eclipse")"
    read -r download_url checksum < <(python3 -c '
import json, sys
assets = json.load(sys.stdin)
if not assets:
    raise SystemExit("no matching Temurin JDK asset returned")
package = assets[0]["binary"]["package"]
print(package["link"], package["checksum"])
' <<< "$metadata")
    [[ -n "$download_url" && -n "$checksum" ]] \
        || fail "the Temurin API returned incomplete JDK metadata"

    download_dir="$(mktemp -d)"
    archive="$download_dir/temurin-jdk-21.tar.gz"
    install -d "$install_parent"
    [[ ! -e "$install_dir" ]] \
        || fail "an incomplete local JDK already exists: $install_dir"
    temporary_install="$(mktemp -d "$install_parent/.jdk-21.XXXXXX")"
    trap 'rm -rf -- "$download_dir" "$temporary_install"' RETURN

    echo "Downloading Eclipse Temurin 21 JDK"
    curl --fail --location --retry 3 --output "$archive" "$download_url"
    echo "$checksum  $archive" | sha256sum --check --status \
        || fail "invalid checksum for downloaded Temurin JDK"
    tar -xzf "$archive" -C "$temporary_install" --strip-components=1
    [[ -x "$temporary_install/bin/java" ]] \
        || fail "the downloaded Temurin archive does not contain a JDK"
    mv "$temporary_install" "$install_dir"
    rm -rf -- "$download_dir"
    trap - RETURN
    echo "Installed Eclipse Temurin JDK 21 in $install_dir"
}

find_sdkmanager() {
    local sdk_path="$1" candidate
    for candidate in \
        "$sdk_path/cmdline-tools/latest/bin/sdkmanager" \
        "$sdk_path/tools/bin/sdkmanager"; do
        if [[ -x "$candidate" ]]; then
            echo "$candidate"
            return
        fi
    done
    find "$sdk_path/cmdline-tools" -mindepth 3 -maxdepth 3 \
        -path '*/bin/sdkmanager' -type f -perm -u+x -print 2>/dev/null \
        | sort -V | tail -1 || true
}

bootstrap() {
    local option="${1:-}" sdk_path="" sdkmanager="" candidate java_home
    case "$option" in
        ""|--system-packages|--with-deps) ;;
        --check) doctor; return ;;
        *) fail "unsupported bootstrap option: $option" ;;
    esac

    echo "Bootstrapping the Pico 4 build environment"
    install_system_packages
    if [[ "$option" == "--system-packages" ]]; then
        echo
        doctor
        return
    fi
    install_compatible_jdk

    export PATH="${HOME}/.local/bin:$PATH"
    if ! find_conan >/dev/null || ! run_conan --version 2>/dev/null | grep -q '^Conan version 2\.'; then
        command -v pipx >/dev/null \
            || fail "pipx was not installed; see https://pipx.pypa.io/stable/how-to/install-pipx.html"
        echo "Installing Conan 2 in an isolated pipx environment"
        pipx install --force 'conan>=2,<3'
    fi
    if ! run_conan profile path default >/dev/null 2>&1; then
        echo "Creating the Conan default profile"
        run_conan profile detect --force
    fi

    for candidate in "${ANDROID_SDK_ROOT:-}" "${ANDROID_HOME:-}" "${HOME}/Android/Sdk"; do
        if [[ -n "$candidate" && -d "$candidate" ]]; then
            sdk_path="$candidate"
            break
        fi
    done
    if [[ -z "$sdk_path" ]]; then
        sdk_path="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}"
    fi
    sdkmanager="$(find_sdkmanager "$sdk_path")"
    if [[ -z "$sdkmanager" ]]; then
        install_android_command_line_tools "$sdk_path"
        sdkmanager="$(find_sdkmanager "$sdk_path")"
    fi
    [[ -x "$sdkmanager" ]] || fail "sdkmanager installation failed"

    java_home="$(find_compatible_jdk || true)"
    [[ -z "$java_home" ]] || export JAVA_HOME="$java_home"
    echo "Review and accept the Android SDK component licenses when prompted"
    "$sdkmanager" --sdk_root="$sdk_path" --licenses
    echo "Installing Android SDK Platform 36, Build-Tools, CMake, NDK, and Platform-Tools"
    "$sdkmanager" --sdk_root="$sdk_path" \
        "platforms;android-36" "build-tools;36.0.0" \
        "cmake;$android_cmake_version" "ndk;27.3.13750724" "platform-tools"
    export ANDROID_SDK_ROOT="$sdk_path"
    export ANDROID_HOME="$sdk_path"

    echo
    doctor
    if [[ "$option" == "--with-deps" ]]; then
        echo
        download_prebuilt_dependencies
    fi
}

newest_match() {
    local pattern="$1"
    find "$conan_home/p/b" -maxdepth 7 -path "$pattern" -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr | sed -n '1s/^[^ ]* //p'
}

newest_host_tool() {
    local pattern="$1" candidate
    while IFS= read -r candidate; do
        if file "$candidate" | grep -Eq 'x86-64|x86_64'; then
            echo "$candidate"
            return
        fi
    done < <(find "$conan_home/p" -maxdepth 8 -path "$pattern" \
        -type f -perm -u+x -printf '%T@ %p\n' 2>/dev/null \
        | sort -nr | sed 's/^[^ ]* //')
}

detect_sdk() {
    local candidate
    for candidate in "${ANDROID_SDK_ROOT:-}" "${ANDROID_HOME:-}" "${HOME}/Android/Sdk"; do
        if [[ -n "$candidate" && -d "$candidate/platforms/android-36" ]]; then
            export ANDROID_SDK_ROOT="$candidate"
            export ANDROID_HOME="$candidate"
            return
        fi
    done
    fail "Android SDK 36 not found; set ANDROID_SDK_ROOT (install: $android_tools_url)"
}

java_major() {
    "$1/bin/java" -version 2>&1 | sed -n '1s/.*version "\([0-9]*\).*/\1/p'
}

find_compatible_jdk() {
    local candidate major java_path
    local -a candidates=(
        "${JAVA_HOME:-}"
        "${HOME}/Applications/android-studio/jbr"
        "$script_dir/pico-host-tools/jdk-21"
        "/opt/android-studio/jbr"
        "/usr/lib/jvm/java-21-openjdk"
        "/usr/lib/jvm/java-21-openjdk-amd64"
    )
    java_path="$(command -v java 2>/dev/null || true)"
    if [[ -n "$java_path" ]]; then
        java_path="$(readlink -f "$java_path")"
        candidates+=("${java_path%/bin/java}")
    fi
    for candidate in "${candidates[@]}"; do
        [[ -n "$candidate" && -x "$candidate/bin/java" ]] || continue
        major="$(java_major "$candidate")"
        if [[ "$major" =~ ^[0-9]+$ && "$major" -ge 17 && "$major" -le 21 ]]; then
            echo "$candidate"
            return
        fi
    done
    return 1
}

detect_jdk() {
    local candidate
    candidate="$(find_compatible_jdk || true)"
    if [[ -n "$candidate" ]]; then
        export JAVA_HOME="$candidate"
        return
    fi
    fail "a JDK between versions 17 and 21 was not found; set JAVA_HOME (install: $android_tools_url)"
}

detect_dependencies() {
    local qt_build qt_source draco_package draco_member tbb_package

    local draco_conan_data="$android_root/common/conan/pico4-debug/generators/draco-debug-armv8-data.cmake"
    if [[ -z "${PICO_DRACO_PACKAGE_DIR:-}" && -f "$draco_conan_data" ]]; then
        draco_package="$(sed -n 's/^set(draco_PACKAGE_FOLDER_DEBUG "\(.*\)")$/\1/p' "$draco_conan_data" | head -n 1)"
    fi

    draco_package="${PICO_DRACO_PACKAGE_DIR:-${draco_package:-$(newest_match '*/draco*/p/lib/libdraco.a')}}"
    [[ -n "$draco_package" ]] || fail "Draco Conan package not found; set PICO_DRACO_PACKAGE_DIR"
    [[ "$draco_package" != *.a ]] || draco_package="${draco_package%/lib/libdraco.a}"
    read -r draco_member < <(ar t "$draco_package/lib/libdraco.a")
    [[ -n "$draco_member" ]] || fail "Draco archive is empty: $draco_package/lib/libdraco.a"
    ar p "$draco_package/lib/libdraco.a" "$draco_member" | file - | grep -Eq 'ARM aarch64|ARM64' \
        || fail "Draco library is not Android ARM64: $draco_package/lib/libdraco.a"

    export PICO_DRACO_PACKAGE_DIR="$draco_package"
    if [[ ! -f "$script_dir/../../common/runtime-overrides/arm64-v8a/.prebuilt-runtime" ]]; then
        qt_build="${PICO_QT_BUILD_DIR:-$(newest_match '*/qt*/b/build_folder/qtbase/lib/libQt5Core_arm64-v8a.so')}"
        [[ -n "$qt_build" ]] || fail "patched Qt build not found; set PICO_QT_BUILD_DIR"
        [[ "$qt_build" != *.so ]] || qt_build="${qt_build%/qtbase/lib/libQt5Core_arm64-v8a.so}"
        qt_source="${PICO_QT_SOURCE_DIR:-${qt_build%/build_folder}/qt5}"
        [[ -d "$qt_source" ]] || fail "matching Qt source not found; set PICO_QT_SOURCE_DIR"

        tbb_package="${PICO_TBB_PACKAGE_DIR:-$(newest_match '*/onetb*/p/lib/libtbb.so')}"
        [[ -n "$tbb_package" ]] || fail "release TBB Conan package not found; set PICO_TBB_PACKAGE_DIR"
        [[ "$tbb_package" != *.so ]] || tbb_package="${tbb_package%/lib/libtbb.so}"
        file "$tbb_package/lib/libtbb.so" | grep -Eq 'ARM aarch64|ARM64' \
            || fail "TBB runtime is not Android ARM64: $tbb_package/lib/libtbb.so"

        export PICO_QT_BUILD_DIR="$qt_build"
        export PICO_QT_SOURCE_DIR="$qt_source"
        export PICO_TBB_PACKAGE_DIR="$tbb_package"
    fi
    export PICO_GLSLANG_VALIDATOR="${PICO_GLSLANG_VALIDATOR:-$(newest_host_tool '*/glsl*/p/bin/glslang')}"
    export PICO_SCRIBE="${PICO_SCRIBE:-$(newest_host_tool '*/scrib*/p/tools/scribe')}"
    export PICO_SPIRV_CROSS="${PICO_SPIRV_CROSS:-$(newest_host_tool '*/spirv*/p/bin/spirv-cross')}"
    export PICO_SPIRV_OPT="${PICO_SPIRV_OPT:-$(newest_host_tool '*/spirv*/p/bin/spirv-opt')}"

    local tool
    for tool in PICO_GLSLANG_VALIDATOR PICO_SCRIBE PICO_SPIRV_CROSS PICO_SPIRV_OPT; do
        [[ -x "${!tool:-}" ]] || fail "host tool $tool not found; set it explicitly"
    done

    if [[ -f "$script_dir/../../common/runtime-overrides/arm64-v8a/.prebuilt-runtime" ]]; then
        echo "Runtime: downloaded prebuilt artifacts"
    else
        echo "Qt build: $PICO_QT_BUILD_DIR"
        echo "TBB package: $PICO_TBB_PACKAGE_DIR"
    fi
    echo "Draco package: $PICO_DRACO_PACKAGE_DIR"
}

install_dependencies() {
    find_conan >/dev/null || fail "Conan 2 was not found (install: $conan_install_url)"
    detect_sdk
    export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-$ANDROID_SDK_ROOT/ndk/27.3.13750724}"
    [[ -d "$ANDROID_NDK_HOME" ]] \
        || fail "Android NDK 27.3.13750724 not found: $ANDROID_NDK_HOME"

    echo "Configuring the official Overte Conan repository"
    run_conan remote add overte "$overte_conan_url" --force

    # Phone Qt rebuilds share this pinned module. Always provision it even when
    # the host Perl happens to provide English.pm globally; otherwise Pico deps
    # can succeed while the immediately following Phone producer fails.
    local perl_module_dir="$script_dir/pico-host-tools/perl"
    local perl_module="$perl_module_dir/English.pm"
    command -v curl >/dev/null || fail "curl is required to install the Perl English module"
    install -d "$perl_module_dir"
    if [[ ! -f "$perl_module" ]]; then
        echo "Downloading the Perl English module required by Qt"
        curl --fail --location --retry 3 --output "$perl_module" \
            https://raw.githubusercontent.com/Perl/perl5/v5.42.0/lib/English.pm
    fi
    echo "f857b95e26385272525a7519267c8c63648d692608b7633b46d267c38092ccb3  $perl_module" \
        | sha256sum --check --status \
        || fail "invalid checksum for downloaded Perl English module"
    export PERL5LIB="$perl_module_dir${PERL5LIB:+:$PERL5LIB}"

    echo "Exporting local Pico recipes"
    run_conan export "$android_root/common/conan/recipes/libnode"
    run_conan export "$android_root/common/conan/recipes/nvidia-texture-tools"
    run_conan export "$android_root/common/conan/recipes/onetbb-local" --version=2021.10.0

    echo "Installing native shader tools"
    run_conan install "$android_root/common/conan/conanfile-pico-host-tools.py" \
        -of "$android_root/common/conan/pico4-host" \
        -pr:h default -pr:b default -c "tools.build:jobs=$jobs" --build=missing

    echo "Installing Android ARM64 dependencies"
    run_conan install "$android_root/common/conan/conanfile-pico.py" \
        -of "$android_root/common/conan/pico4-debug" \
        -pr:h "$android_root/common/conan/profiles/pico4-arm64" \
        -pr:b default -c "tools.build:jobs=$jobs" --build=missing

    echo "Installing the Android ARM64 release TBB runtime"
    run_conan install --requires=onetbb/2021.10.0 \
        -of "$android_root/common/conan/pico4-tbb-release" \
        -pr:h "$android_root/common/conan/profiles/pico4-arm64" \
        -pr:b default -c "tools.build:jobs=$jobs" \
        -s:h build_type=Release --build=missing

    if [[ ! -f "$script_dir/../../common/runtime-overrides/arm64-v8a/.prebuilt-runtime" \
        && -z "$(newest_match '*/qt*/b/build_folder/qtbase/lib/libQt5Core_arm64-v8a.so')" \
        && -z "$(newest_match '*/qt*/p/lib/libQt5Core_arm64-v8a.so')" ]]; then
        echo "No local Qt build tree found; building Qt from source (this can take a long time)"
        run_conan install "$android_root/common/conan/conanfile-pico.py" \
            -of "$android_root/common/conan/pico4-debug" \
            -pr:h "$android_root/common/conan/profiles/pico4-arm64" \
            -pr:b default -c "tools.build:jobs=$jobs" \
            --build=missing --build='qt/*'
    fi

    echo "Installed Pico dependencies"
}

download_prebuilt_dependencies() {
    local checksums="$android_root/common/conan/prebuilt/${prebuilt_tag}.sha256"
    local base_url="https://github.com/noah-be/overte/releases/download/${prebuilt_tag}"
    local download_dir asset qt_source_dir
    local legacy_runtime_dir="$script_dir/apps/picoInterface/src/main/runtime-overrides/arm64-v8a"
    local shared_runtime_dir="$script_dir/../../common/runtime-overrides/arm64-v8a"

    find_conan >/dev/null || fail "Conan 2 was not found (install: $conan_install_url)"
    command -v curl >/dev/null || fail "curl is not installed or not in PATH"
    [[ -f "$checksums" ]] || fail "prebuilt checksum manifest not found: $checksums"
    download_dir="$(mktemp -d)"
    trap 'rm -rf -- "$download_dir"' RETURN

    while read -r _ asset; do
        [[ -n "$asset" ]] || continue
        echo "Downloading $asset"
        curl --fail --location --retry 3 \
            --output "$download_dir/$asset" "$base_url/$asset"
    done < "$checksums"

    (cd "$download_dir" && sha256sum --check "$checksums")
    run_conan cache restore "$download_dir/pico4-qt-conan.tgz"
    run_conan cache restore "$download_dir/pico4-node-conan.tgz"
    tar -xzf "$download_dir/pico4-runtime.tgz" -C "$script_dir"
    # pico4-deps-v1 predates the shared Android runtime directory. Keep that
    # immutable release usable while new archives adopt the shared layout.
    if [[ -f "$legacy_runtime_dir/.prebuilt-runtime" ]]; then
        install -d "$shared_runtime_dir"
        cp -a "$legacy_runtime_dir/." "$shared_runtime_dir/"
        echo "Published Pico runtime copied into the shared Android runtime directory"
    fi
    echo "Restored prebuilt Pico Qt, Node, and runtime artifacts"
    rm -rf -- "$download_dir"
    trap - RETURN

    # Phone setup restores a complete, separately verified 16 KiB Conan graph
    # next. It only needs the shared cache and runtime payload from this step;
    # resolving the Pico graph here can otherwise rebuild Node/V8 needlessly.
    if [[ "${PICO_PREBUILT_RESTORE_ONLY:-0}" == 1 ]]; then
        echo "Skipped Pico dependency resolution after artifact restore"
        return
    fi

    if [[ -n "${PICO_QT_FALLBACK_PATCH:-}" ]]; then
        qt_source_dir="$(run_conan cache path "$qt_reference" --folder=source)"
        [[ -d "$qt_source_dir/qt5" ]] \
            || fail "Qt sources are missing for the requested fallback patch"
        with_temporary_git_patch "$PICO_QT_FALLBACK_PATCH" "$qt_source_dir/qt5" \
            install_dependencies
    else
        install_dependencies
    fi
}

prepare() {
    detect_dependencies
    PICO_BUILD_JOBS="$jobs" "$script_dir/prepare-deps.sh"
}

build() {
    local option="${1:-}"
    local variant="${2:-debug}" task output
    local -a gradle_diagnostics=()
    if [[ "$option" == "--stacktrace" ]]; then
        gradle_diagnostics+=(--stacktrace)
    elif [[ -n "$option" ]]; then
        fail "unsupported build option: $option"
    fi
    detect_sdk
    detect_jdk
    if [[ "$variant" == "release" ]]; then
        task=assembleRelease
        output="$script_dir/apps/picoInterface/build/outputs/apk/release/picoInterface-release.apk"
    else
        task=assembleDebug
        output="$script_dir/apps/picoInterface/build/outputs/apk/debug/picoInterface-debug.apk"
    fi
    echo "Android SDK: $ANDROID_SDK_ROOT"
    echo "Java: $JAVA_HOME"
    PICO_BUILD_JOBS="$jobs" CMAKE_BUILD_PARALLEL_LEVEL="$jobs" \
        SHADERGEN_JOBS="${PICO_SHADER_JOBS:-$jobs}" \
        "$android_root/common/gradlew" \
        --settings-file "$script_dir/settings.gradle" \
        ":picoInterface:$task" --max-workers="$jobs" "${gradle_diagnostics[@]}"
    echo "APK: $output"
}

install_apk() {
    local adb apk serial install_output
    local -a devices

    if [[ "${PICO_DEVICE_LOCK_HELD:-0}" != 1 ]]; then
        exec "$script_dir/pico-device-lock.sh" run -- "$0" install
    fi
    detect_sdk
    adb="${PICO_ADB:-$ANDROID_SDK_ROOT/platform-tools/adb}"
    [[ -x "$adb" ]] || fail "ADB not found; install Android SDK Platform-Tools or set PICO_ADB"
    apk="$script_dir/apps/picoInterface/build/outputs/apk/debug/picoInterface-debug.apk"
    [[ -f "$apk" ]] || fail "APK not found; run ./build-pico.sh build first"

    if [[ -n "${ANDROID_SERIAL:-}" ]]; then
        serial="$ANDROID_SERIAL"
        "$adb" -s "$serial" get-state >/dev/null \
            || fail "ADB device is not available: $serial"
    else
        mapfile -t devices < <("$adb" devices | awk '$2 == "device" { print $1 }')
        if [[ "${#devices[@]}" -eq 0 ]]; then
            fail "no authorized ADB device found; connect the Pico and allow USB debugging"
        fi
        if [[ "${#devices[@]}" -gt 1 ]]; then
            fail "multiple ADB devices found; select one with ANDROID_SERIAL=<serial>"
        fi
        serial="${devices[0]}"
    fi

    echo "Installing APK on $serial"
    if ! install_output="$("$adb" -s "$serial" install -r "$apk" 2>&1)"; then
        printf '%s\n' "$install_output" >&2
        if [[ "$install_output" == *INSTALL_FAILED_UPDATE_INCOMPATIBLE* ]]; then
            echo >&2
            echo "The installed org.overte.pico app was signed with a different key." >&2
            echo "Android cannot update it with this development APK." >&2
            echo "Uninstall the existing app first (this deletes its local app data):" >&2
            printf '  %q -s %q uninstall org.overte.pico\n' "$adb" "$serial" >&2
            echo "Then retry:" >&2
            echo "  ./build-pico.sh install" >&2
            exit 2
        fi
        fail "ADB could not install the Pico APK"
    fi
    printf '%s\n' "$install_output"
    echo "Starting org.overte.pico on $serial"
    "$adb" -s "$serial" shell am start -W \
        -a android.intent.action.MAIN \
        -c android.intent.category.LAUNCHER \
        -n org.overte.pico/.PermissionsActivity
    "$adb" -s "$serial" shell pidof org.overte.pico >/dev/null \
        || fail "the APK was installed, but org.overte.pico did not stay running"
    echo "Installed and started org.overte.pico on $serial"
}

case "$command_name" in
    doctor) doctor ;;
    bootstrap) bootstrap "$command_option" ;;
    deps)
        if [[ "$command_option" == "--download" ]]; then
            download_prebuilt_dependencies
        elif [[ -z "$command_option" ]]; then
            install_dependencies
        else
            fail "unsupported deps option: $command_option"
        fi
        ;;
    prepare) prepare ;;
    build) build "$command_option" debug ;;
    release) build "$command_option" release ;;
    install) install_apk ;;
    all) prepare; build ;;
    deploy) prepare; build; install_apk ;;
    setup)
        doctor
        echo
        if [[ "$command_option" == "--download" ]]; then
            download_prebuilt_dependencies
        elif [[ -z "$command_option" ]]; then
            install_dependencies
        else
            fail "unsupported setup option: $command_option"
        fi
        prepare
        build
        ;;
    help|-h|--help) usage ;;
    *) usage >&2; fail "unknown command: $command_name" ;;
esac
