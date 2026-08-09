#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
tag='android-phone-16k-deps-v1'
asset='android-phone-16k-conan.tgz'
manifest="${PHONE_PREBUILT_MANIFEST:-$script_dir/conan/prebuilt/${tag}.sha256}"
base_url="${PHONE_PREBUILT_BASE_URL:-https://github.com/noah-be/overte/releases/download/$tag}"
qt_profile="$script_dir/conan/profiles/phone-arm64-16k"
nonqt_profile="$script_dir/conan/profiles/phone-nonqt-arm64-16k"
conanfile="$script_dir/conan/conanfile-pico.py"
qt_output="$script_dir/conan/phone-16k-debug"
nonqt_output="$script_dir/conan/phone-nonqt-16k-debug"
ready_marker="${PHONE_PREBUILT_READY_MARKER:-$nonqt_output/.phone-16k-dependencies.ready}"
finalizer="${PHONE_PREBUILT_FINALIZER:-$script_dir/finalize-phone-16k-deps.sh}"
qt_package='qt/5.15.18-2026.01.04@overte/stable#d59ba2a04fe9ede772b05b0bb0865eb0:ecaa689b690ceb46b802551d031b4fd0b54cf970'

fail() {
    echo "error: $*" >&2
    exit 2
}

find_conan() {
    local candidate
    for candidate in \
        "${PHONE_CONAN:-}" \
        "$(command -v conan 2>/dev/null || true)" \
        "${HOME}/.local/bin/conan"; do
        [[ -n "$candidate" && -x "$candidate" ]] || continue
        printf '%s\n' "$candidate"
        return
    done
    return 1
}

validate_manifest() {
    local checksum listed_asset extra
    [[ -f "$manifest" ]] || fail "Phone prebuilt checksum manifest is missing"
    read -r checksum listed_asset extra <"$manifest" || fail "Phone prebuilt checksum manifest is empty"
    [[ "$checksum" =~ ^[0-9a-f]{64}$ ]] || fail "Phone prebuilt checksum is invalid"
    [[ "$listed_asset" == "$asset" && -z "${extra:-}" ]] \
        || fail "Phone prebuilt manifest names an unexpected asset"
    [[ "$(awk 'NF { count++ } END { print count + 0 }' "$manifest")" == 1 ]] \
        || fail "Phone prebuilt manifest must contain exactly one asset"
}

generate_outputs() {
    local conan_bin="$1"
    "$conan_bin" install "$conanfile" -of "$qt_output" \
        -pr:h "$qt_profile" -pr:b default --no-remote --build=never
    "$conan_bin" install "$conanfile" -of "$nonqt_output" \
        -pr:h "$nonqt_profile" -pr:b default --no-remote --build=never
    "$finalizer"
    [[ -f "$ready_marker" ]] || fail "Phone dependency finalizer did not publish readiness"
}

download_artifact() {
    local conan_bin curl_bin download_dir
    conan_bin="$(find_conan)" || fail "Conan 2 was not found"
    curl_bin="${PHONE_CURL:-$(command -v curl 2>/dev/null || true)}"
    [[ -n "$curl_bin" && -x "$curl_bin" ]] || fail "curl was not found"
    validate_manifest
    download_dir="$(mktemp -d "${TMPDIR:-/tmp}/overte-phone-16k-download.XXXXXXXX")"
    trap 'rm -rf -- "$download_dir"' RETURN
    echo "Downloading checksum-verified Phone 16 KiB dependency delta"
    "$curl_bin" --fail --location --retry 3 \
        --output "$download_dir/$asset" "$base_url/$asset"
    (cd "$download_dir" && sha256sum --check "$manifest") \
        || fail "Phone prebuilt dependency checksum does not match"
    "$conan_bin" cache restore "$download_dir/$asset"
    generate_outputs "$conan_bin"
    echo "Restored and verified Phone 16 KiB dependencies"
    rm -rf -- "$download_dir"
    trap - RETURN
}

export_artifact() {
    local output_dir="${1:-}" conan_bin archive qt_package_dir
    [[ -n "$output_dir" && "$output_dir" == /* ]] \
        || fail "export requires an absolute output directory"
    conan_bin="$(find_conan)" || fail "Conan 2 was not found"
    "$finalizer"
    [[ -f "$ready_marker" ]] || fail "verified Phone dependencies are not ready"
    mkdir -p -- "$output_dir"
    archive="$output_dir/$asset"
    [[ ! -e "$archive" && ! -e "$output_dir/${tag}.sha256" ]] \
        || fail "export output files already exist"
    qt_package_dir="$($conan_bin cache path "$qt_package")"
    [[ -d "$qt_package_dir" ]] || fail "verified Phone Qt package is missing"
    "$script_dir/tests/check-phone-elf-alignment.sh" "$qt_package_dir"
    "$conan_bin" cache save "$qt_package" --no-source --file="$archive"
    (cd "$output_dir" && sha256sum "$asset") \
        >"$output_dir/${tag}.sha256"
    echo "Created $archive and ${tag}.sha256"
}

case "${1:-}" in
    download) download_artifact ;;
    export) export_artifact "${2:-}" ;;
    *) fail "usage: $0 download | export ABSOLUTE_OUTPUT_DIRECTORY" ;;
esac
