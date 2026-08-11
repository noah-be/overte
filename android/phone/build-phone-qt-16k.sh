#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
android_root="$(cd -- "$script_dir/.." && pwd)"
source "$script_dir/phone-build-resource-guard.sh"
phone_build_resource_guard "$script_dir/$(basename -- "${BASH_SOURCE[0]}")" "$@"
conan_home="${CONAN_HOME:-${HOME}/.conan2}"
output_dir="$android_root/common/conan/phone-16k-debug"
ready_sentinel="$android_root/common/conan/phone-nonqt-16k-debug/.phone-16k-dependencies.ready"
profile="$android_root/common/conan/profiles/phone-arm64-16k"
qt_reference='qt/5.15.18-2026.01.04@overte/stable#d59ba2a04fe9ede772b05b0bb0865eb0'
perl_module_dir="$script_dir/pico-host-tools/perl"
qt_page_patch="$android_root/common/conan/patches/qt-phone-16k-pages.patch"
qt_recipe_patch="$android_root/common/conan/patches/qt-phone-serial-install.patch"
qt_source_dir=""
qt_recipe_dir=""
patch_owned=0
recipe_patch_owned=0

fail() {
    echo "error: $*" >&2
    exit 2
}

find_conan() {
    local candidate
    for candidate in \
        "$(command -v conan 2>/dev/null || true)" \
        "${HOME}/.local/bin/conan" \
        "${PIPX_HOME:-${HOME}/.local/share/pipx}/venvs/conan/bin/conan"; do
        [[ -n "$candidate" && -x "$candidate" ]] || continue
        printf '%s\n' "$candidate"
        return
    done
    return 1
}

verify_alignment() {
    local package_dir
    package_dir="$(sed -n 's/set(qt_PACKAGE_FOLDER_DEBUG "\([^"]*\)")/\1/p' \
        "$output_dir/generators/Qt5-debug-armv8-data.cmake")"
    [[ -d "$package_dir" ]] || fail "Qt package directory was not generated"

    "$android_root/phone/tests/check-phone-elf-alignment.sh" "$package_dir" \
        || fail "the rebuilt Qt package still contains 4 KiB ELF segments"
    echo "Qt package is 16 KiB compatible: $package_dir"
}

cleanup_cache() {
    if (( patch_owned == 1 )); then
        git -C "$qt_source_dir" apply --reverse "$qt_page_patch"
        patch_owned=0
    fi
    if (( recipe_patch_owned == 1 )); then
        git -C "$qt_recipe_dir" apply --reverse "$qt_recipe_patch"
        recipe_patch_owned=0
    fi
}

main() {
    local conan_path source_dir sdk
    conan_path="$(find_conan)" || fail "Conan 2 was not found"
    sdk="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${HOME}/Android/Sdk}}"
    export ANDROID_SDK_ROOT="$sdk"
    export ANDROID_HOME="$sdk"
    export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-$sdk/ndk/27.3.13750724}"
    [[ -d "$ANDROID_NDK_HOME" ]] || fail "Android NDK 27.3.13750724 was not found"

    # Neither Gradle nor a concurrent dependency job may treat an older,
    # cross-package verification result as valid while Qt is being replaced.
    rm -f -- "$ready_sentinel"

    source_dir="$($conan_path cache path "$qt_reference" --folder=source 2>/dev/null || true)"
    [[ -d "$source_dir/qt5" ]] \
        || fail "Qt sources are not in the local Conan cache; run the dependency setup first"
    [[ -f "$perl_module_dir/English.pm" ]] \
        || fail "pico-host-tools/perl/English.pm is missing; run the dependency setup first"
    export PERL5LIB="$perl_module_dir${PERL5LIB:+:$PERL5LIB}"

    qt_source_dir="$source_dir/qt5"
    if git -C "$qt_source_dir" apply --reverse --check "$qt_page_patch" >/dev/null 2>&1; then
        echo "Removing a 16 KiB patch left by an interrupted earlier run"
        git -C "$qt_source_dir" apply --reverse "$qt_page_patch"
    fi
    git -C "$qt_source_dir" apply --check "$qt_page_patch"
    git -C "$qt_source_dir" apply "$qt_page_patch"
    patch_owned=1

    qt_recipe_dir="$($conan_path cache path "$qt_reference" 2>/dev/null || true)"
    [[ -f "$qt_recipe_dir/conanfile.py" ]] \
        || fail "the pinned Qt recipe is not in the local Conan cache"
    if git -C "$qt_recipe_dir" apply --reverse --check "$qt_recipe_patch" >/dev/null 2>&1; then
        echo "Removing a serial-install patch left by an interrupted earlier run"
        git -C "$qt_recipe_dir" apply --reverse "$qt_recipe_patch"
    fi
    git -C "$qt_recipe_dir" apply --check "$qt_recipe_patch"
    git -C "$qt_recipe_dir" apply "$qt_recipe_patch"
    recipe_patch_owned=1
    trap cleanup_cache EXIT

    echo "Rebuilding Qt locally with 16 KiB ELF alignment"
    echo "Source cache: $source_dir"
    echo "Output: $output_dir"
    "$conan_path" install "$android_root/common/conan/conanfile-pico.py" \
        -of "$output_dir" \
        -pr:h "$profile" \
        -pr:b default \
        -nr \
        --build='qt/*'
    verify_alignment
    cleanup_cache
    trap - EXIT
}

main "$@"
