#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
conan_home="${CONAN_HOME:-${HOME}/.conan2}"
jobs="${PICO_BUILD_JOBS:-$(nproc)}"
command_name="${1:-all}"
command_option="${2:-}"
prebuilt_tag="pico4-deps-v1"
android_tools_url="https://developer.android.com/studio"
platform_tools_url="https://developer.android.com/tools/releases/platform-tools"
conan_install_url="https://docs.conan.io/2/installation.html"
cmake_install_url="https://cmake.org/download/"
ninja_install_url="https://github.com/ninja-build/ninja/releases"
git_install_url="https://git-scm.com/downloads"
python_install_url="https://www.python.org/downloads/"
perl_install_url="https://www.perl.org/get.html"

fail() {
    echo "error: $*" >&2
    exit 2
}

usage() {
    cat <<'EOF'
Usage: ./build-pico.sh [doctor|bootstrap|deps|prepare|build|install|all|deploy|setup] [option]

  doctor   Check the development environment and print installation help
  bootstrap [--check|--system-packages|--with-deps]
           Install as many missing build requirements as possible
  deps     Install dependencies; use --download for prebuilt Qt and Node
  prepare  Locate and stage the existing Conan/Qt dependencies
  build    Build the Pico debug APK
  install  Install the existing APK on a connected Pico via ADB
  all      Prepare dependencies and build the APK (default)
  deploy   Prepare, build, and install the APK
  setup    Install dependencies, prepare them, and build the APK

Detected paths can be overridden with ANDROID_SDK_ROOT, JAVA_HOME,
PICO_QT_SOURCE_DIR, PICO_QT_BUILD_DIR, PICO_TBB_PACKAGE_DIR,
PICO_DRACO_PACKAGE_DIR, and the PICO_* host-tool variables.
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

    if command_path="$(command -v conan 2>/dev/null)"; then
        version="$(conan --version 2>/dev/null || true)"
        if [[ "$version" =~ Conan\ version\ 2\. ]]; then
            doctor_ok "$version ($command_path)"
            if conan profile path default >/dev/null 2>&1; then
                doctor_ok "Conan default profile"
            else
                doctor_error "the Conan default profile is missing"
                echo "           Create it with: conan profile detect --force"
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

    for tool in file make ar tar sha256sum; do
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

    if [[ -x "$script_dir/gradlew" ]]; then
        doctor_ok "Gradle wrapper ($script_dir/gradlew)"
    else
        doctor_error "the project Gradle wrapper is missing or not executable"
    fi

    free_kb="$(df -Pk "$script_dir" | awk 'NR == 2 { print $4 }')"
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
    for tool in git curl cmake ninja python3 perl file make ar tar sha256sum unzip; do
        command -v "$tool" >/dev/null 2>&1 || needs_packages=1
    done
    [[ -n "$(find_compatible_jdk || true)" ]] || needs_packages=1
    command -v conan >/dev/null 2>&1 || command -v pipx >/dev/null 2>&1 || needs_packages=1

    if [[ "$needs_packages" -eq 0 ]]; then
        echo "System build tools are already installed"
        return
    fi

    echo "Installing missing system build tools (administrator access may be requested)"
    if command -v dnf >/dev/null; then
        run_as_root dnf install -y git curl cmake ninja-build python3 python3-pip \
            pipx perl file make binutils tar coreutils unzip java-21-openjdk-devel
    elif command -v apt-get >/dev/null; then
        run_as_root apt-get update
        run_as_root apt-get install -y git curl cmake ninja-build python3 python3-pip \
            pipx perl file make binutils tar coreutils unzip openjdk-21-jdk
    elif command -v pacman >/dev/null; then
        run_as_root pacman -S --needed --noconfirm git curl cmake ninja python \
            python-pipx perl file make binutils tar coreutils unzip jdk21-openjdk
    elif command -v zypper >/dev/null; then
        run_as_root zypper --non-interactive install git curl cmake ninja python3 \
            python3-pipx perl file make binutils tar gzip coreutils unzip \
            java-21-openjdk-devel
    else
        fail "unsupported package manager; install the items reported by ./build-pico.sh doctor"
    fi
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

    export PATH="${HOME}/.local/bin:$PATH"
    if ! command -v conan >/dev/null || ! conan --version 2>/dev/null | grep -q '^Conan version 2\.'; then
        command -v pipx >/dev/null \
            || fail "pipx was not installed; see https://pipx.pypa.io/stable/how-to/install-pipx.html"
        echo "Installing Conan 2 in an isolated pipx environment"
        pipx install --force 'conan>=2,<3'
    fi
    if ! conan profile path default >/dev/null 2>&1; then
        echo "Creating the Conan default profile"
        conan profile detect --force
    fi

    for candidate in "${ANDROID_SDK_ROOT:-}" "${ANDROID_HOME:-}" "${HOME}/Android/Sdk"; do
        if [[ -n "$candidate" && -d "$candidate" ]]; then
            sdk_path="$candidate"
            break
        fi
    done
    if [[ -z "$sdk_path" ]]; then
        echo "Android command-line tools require acceptance of Google's license terms."
        echo "Install them once from: $android_tools_url"
        echo "Then rerun this command; SDK 36, NDK, and ADB will be installed automatically."
    else
        sdkmanager="$(find_sdkmanager "$sdk_path")"
        if [[ -z "$sdkmanager" ]]; then
            echo "Android SDK found at $sdk_path, but sdkmanager is missing."
            echo "Install the official command-line tools: $android_tools_url"
        else
            java_home="$(find_compatible_jdk || true)"
            [[ -z "$java_home" ]] || export JAVA_HOME="$java_home"
            echo "Review and accept the Android SDK licenses when prompted"
            "$sdkmanager" --sdk_root="$sdk_path" --licenses
            echo "Installing Android SDK Platform 36, NDK, and Platform-Tools"
            "$sdkmanager" --sdk_root="$sdk_path" \
                "platforms;android-36" "build-tools;36.0.0" \
                "ndk;27.3.13750724" "platform-tools"
            export ANDROID_SDK_ROOT="$sdk_path"
            export ANDROID_HOME="$sdk_path"
        fi
    fi

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
    done < <(find "$conan_home/p/b" -maxdepth 7 -path "$pattern" \
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
    local qt_build qt_source draco_package tbb_package

    draco_package="${PICO_DRACO_PACKAGE_DIR:-$(newest_match '*/draco*/p/lib/libdraco.a')}"
    [[ -n "$draco_package" ]] || fail "Draco Conan package not found; set PICO_DRACO_PACKAGE_DIR"
    [[ "$draco_package" != *.a ]] || draco_package="${draco_package%/lib/libdraco.a}"

    export PICO_DRACO_PACKAGE_DIR="$draco_package"
    if [[ ! -f "$script_dir/apps/picoInterface/src/main/runtime-overrides/arm64-v8a/.prebuilt-runtime" ]]; then
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

    if [[ -f "$script_dir/apps/picoInterface/src/main/runtime-overrides/arm64-v8a/.prebuilt-runtime" ]]; then
        echo "Runtime: downloaded prebuilt artifacts"
    else
        echo "Qt build: $PICO_QT_BUILD_DIR"
        echo "TBB package: $PICO_TBB_PACKAGE_DIR"
    fi
    echo "Draco package: $PICO_DRACO_PACKAGE_DIR"
}

install_dependencies() {
    command -v conan >/dev/null || fail "Conan 2 is not installed or not in PATH (install: $conan_install_url)"
    detect_sdk
    export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-$ANDROID_SDK_ROOT/ndk/27.3.13750724}"
    [[ -d "$ANDROID_NDK_HOME" ]] \
        || fail "Android NDK 27.3.13750724 not found: $ANDROID_NDK_HOME"

    if ! perl -MEnglish -e 1 >/dev/null 2>&1; then
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
    fi

    echo "Exporting local Pico recipes"
    conan export "$script_dir/conan/recipes/libnode"
    conan export "$script_dir/conan/recipes/nvidia-texture-tools"
    conan export "$script_dir/conan/recipes/onetbb-local" --version=2021.10.0

    echo "Installing native shader tools"
    conan install "$script_dir/conan/conanfile-pico-host-tools.py" \
        -of "$script_dir/conan/pico4-host" \
        -pr:h default -pr:b default --build=missing

    echo "Installing Android ARM64 dependencies"
    conan install "$script_dir/conan/conanfile-pico.py" \
        -of "$script_dir/conan/pico4-debug" \
        -pr:h "$script_dir/conan/profiles/pico4-arm64" \
        -pr:b default --build=missing

    echo "Installing the Android ARM64 release TBB runtime"
    conan install --requires=onetbb/2021.10.0 \
        -of "$script_dir/conan/pico4-tbb-release" \
        -pr:h "$script_dir/conan/profiles/pico4-arm64" \
        -pr:b default -s:h build_type=Release --build=missing

    if [[ ! -f "$script_dir/apps/picoInterface/src/main/runtime-overrides/arm64-v8a/.prebuilt-runtime" \
        && -z "$(newest_match '*/qt*/b/build_folder/qtbase/lib/libQt5Core_arm64-v8a.so')" ]]; then
        echo "No local Qt build tree found; building Qt from source (this can take a long time)"
        conan install "$script_dir/conan/conanfile-pico.py" \
            -of "$script_dir/conan/pico4-debug" \
            -pr:h "$script_dir/conan/profiles/pico4-arm64" \
            -pr:b default --build=missing --build='qt/*'
    fi

    echo "Installed Pico dependencies"
}

download_prebuilt_dependencies() {
    local checksums="$script_dir/conan/prebuilt/${prebuilt_tag}.sha256"
    local base_url="https://github.com/noah-be/overte/releases/download/${prebuilt_tag}"
    local download_dir asset

    command -v conan >/dev/null || fail "Conan 2 is not installed or not in PATH (install: $conan_install_url)"
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
    conan cache restore "$download_dir/pico4-qt-conan.tgz"
    conan cache restore "$download_dir/pico4-node-conan.tgz"
    tar -xzf "$download_dir/pico4-runtime.tgz" -C "$script_dir"
    echo "Restored prebuilt Pico Qt, Node, and runtime artifacts"

    install_dependencies
}

prepare() {
    detect_dependencies
    PICO_BUILD_JOBS="$jobs" "$script_dir/prepare-pico-deps.sh"
}

build() {
    detect_sdk
    detect_jdk
    echo "Android SDK: $ANDROID_SDK_ROOT"
    echo "Java: $JAVA_HOME"
    CMAKE_BUILD_PARALLEL_LEVEL="$jobs" "$script_dir/gradlew" \
        --settings-file "$script_dir/settings-pico.gradle" \
        :picoInterface:assembleDebug --max-workers="$jobs"
    echo "APK: $script_dir/apps/picoInterface/build/outputs/apk/debug/picoInterface-debug.apk"
}

install_apk() {
    local adb apk serial
    local -a devices

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
    "$adb" -s "$serial" install -r "$apk"
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
    build) build ;;
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
