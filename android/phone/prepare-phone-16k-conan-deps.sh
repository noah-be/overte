#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
android_root="$(cd -- "$script_dir/.." && pwd)"
source "$script_dir/phone-build-resource-guard.sh"
phone_build_resource_guard "$script_dir/$(basename -- "${BASH_SOURCE[0]}")" "$@"
conan_home="${CONAN_HOME:-${HOME}/.conan2}"
profile="$android_root/common/conan/profiles/phone-nonqt-arm64-16k"
output_dir="$android_root/common/conan/phone-nonqt-16k-debug"
ready_sentinel="$output_dir/.phone-16k-dependencies.ready"

# Invalidate an earlier successful run before touching any package. A killed or
# failed rebuild must never leave the phone build looking 16 KiB-ready.
rm -f -- "$ready_sentinel"

find_conan() {
    local candidate
    if command -v conan >/dev/null 2>&1; then
        command -v conan
        return
    fi
    for candidate in \
        "${HOME}/.local/bin/conan" \
        "${PIPX_HOME:-${HOME}/.local/share/pipx}/venvs/conan/bin/conan"; do
        if [[ -x "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return
        fi
    done
    return 1
}

conan_bin="$(find_conan)" || {
    echo "ERROR: Conan 2 was not found." >&2
    exit 1
}

if ! "$conan_bin" --version | grep -q '^Conan version 2\.'; then
    echo "ERROR: Conan 2 is required." >&2
    exit 1
fi

android_sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}"
export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-$android_sdk/ndk/27.3.13750724}"
if [[ ! -d "$ANDROID_NDK_HOME" ]]; then
    echo "ERROR: Android NDK 27.3.13750724 was not found: $ANDROID_NDK_HOME" >&2
    exit 1
fi

# Keep this command offline. A missing source must be addressed explicitly;
# silently downloading a different recipe revision would make the APK audit
# difficult to reproduce.
required_refs=(
    'openssl/1.1.1q'
    'libnode/22.22.3@overte/stable'
    'onetbb/2021.10.0'
    'webrtc-audio-processing/2.1@overte/stable'
)
for ref in "${required_refs[@]}"; do
    if ! "$conan_bin" cache path "$ref" --folder=source >/dev/null 2>&1; then
        echo "ERROR: source for $ref is not available in $conan_home." >&2
        echo "Run ./build-pico.sh deps once with network access, then retry." >&2
        exit 1
    fi
done

echo "Exporting the Android-specific local recipes"
"$conan_bin" export "$android_root/common/conan/recipes/libnode"
"$conan_bin" export "$android_root/common/conan/recipes/onetbb-local" --version=2021.10.0

echo "Rebuilding non-Qt shared dependencies with 16 KiB ELF LOAD alignment"
"$conan_bin" install "$android_root/common/conan/conanfile-pico.py" \
    -of "$output_dir" \
    -pr:h "$profile" \
    -pr:b default \
    --no-remote \
    --build='~qt/*' \
    --build='openssl/*' \
    --build='libnode/*' \
    --build='onetbb/*' \
    --build='webrtc-audio-processing/*'

echo "Generated 16 KiB Conan dependencies in $output_dir"
echo "Verifying the complete Qt and non-Qt package set used by the phone APK"
"$script_dir/finalize-phone-16k-deps.sh"
