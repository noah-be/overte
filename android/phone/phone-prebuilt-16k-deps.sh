#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
android_root="$(cd -- "$script_dir/.." && pwd)"
tag='android-phone-16k-deps-v3'
asset='android-phone-16k-conan.tgz'
manifest="${PHONE_PREBUILT_MANIFEST:-$android_root/common/conan/prebuilt/${tag}.sha256}"
base_url="${PHONE_PREBUILT_BASE_URL:-https://github.com/noah-be/overte/releases/download/$tag}"
qt_profile="$android_root/common/conan/profiles/phone-arm64-16k"
nonqt_profile="$android_root/common/conan/profiles/phone-nonqt-arm64-16k"
build_profile="$android_root/common/conan/profiles/phone-prebuilt-linux-x86_64"
conanfile="$android_root/common/conan/conanfile-pico.py"
qt_output="$android_root/common/conan/phone-16k-debug"
nonqt_output="$android_root/common/conan/phone-nonqt-16k-debug"
ready_marker="${PHONE_PREBUILT_READY_MARKER:-$nonqt_output/.phone-16k-dependencies.ready}"
finalizer="${PHONE_PREBUILT_FINALIZER:-$script_dir/finalize-phone-16k-deps.sh}"
qt_package='qt/5.15.18-2026.01.04@overte/stable#4fc772a2dbcd84731eb6ff9904e6e358:ecaa689b690ceb46b802551d031b4fd0b54cf970'
# The v2 Phone delta published this recipe revision without the complete
# 16 KiB binary. Remove any stale copy before restoring v3; v3 deliberately
# republishes the same revision with the verified Android package. Removing it
# after restore would discard the corrected v3 package and fall back to Pico's
# 4 KiB libnode binary.
incomplete_v2_libnode_recipe='libnode/22.22.3@overte/stable#261cd4344c058c7f08a0fb892519880a'
incomplete_v2_libnode_reference='libnode/22.22.3@overte/stable'
incomplete_v2_libnode_revision='261cd4344c058c7f08a0fb892519880a'

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
        -pr:h "$qt_profile" -pr:b "$build_profile" --no-remote --build=never
    "$conan_bin" install "$conanfile" -of "$nonqt_output" \
        -pr:h "$nonqt_profile" -pr:b "$build_profile" --no-remote --build=never
    "$finalizer"
    [[ -f "$ready_marker" ]] || fail "Phone dependency finalizer did not publish readiness"
}

has_incomplete_v2_libnode_recipe() {
    local conan_bin="$1"
    "$conan_bin" list "$incomplete_v2_libnode_recipe" --format=json | \
        python3 -c '
import json
import sys

payload = json.load(sys.stdin).get("Local Cache", {})
reference = payload.get(sys.argv[1], {})
raise SystemExit(0 if sys.argv[2] in reference.get("revisions", {}) else 1)
' "$incomplete_v2_libnode_reference" "$incomplete_v2_libnode_revision"
}

download_artifact() {
    local conan_bin curl_bin download_dir temp_root
    conan_bin="$(find_conan)" || fail "Conan 2 was not found"
    curl_bin="${PHONE_CURL:-$(command -v curl 2>/dev/null || true)}"
    [[ -n "$curl_bin" && -x "$curl_bin" ]] || fail "curl was not found"
    validate_manifest
    temp_root="${PHONE_PREBUILT_TMPDIR:-$script_dir/build/prebuilt-tmp}"
    [[ ! -L "$temp_root" ]] || fail "Phone prebuilt temporary directory must not be a symlink"
    mkdir -p -- "$temp_root"
    [[ -d "$temp_root" && -w "$temp_root" ]] \
        || fail "Phone prebuilt temporary directory is not writable"
    download_dir="$(mktemp -d "$temp_root/overte-phone-16k-download.XXXXXXXX")"
    trap 'rm -rf -- "${download_dir:-}"' EXIT RETURN
    echo "Downloading checksum-verified Phone 16 KiB dependency graph"
    "$curl_bin" --fail --location --retry 3 \
        --output "$download_dir/$asset" "$base_url/$asset"
    (cd "$download_dir" && sha256sum --check "$manifest") \
        || fail "Phone prebuilt dependency checksum does not match"
    if has_incomplete_v2_libnode_recipe "$conan_bin"; then
        "$conan_bin" remove "$incomplete_v2_libnode_recipe" --confirm >/dev/null
    fi
    "$conan_bin" cache restore "$download_dir/$asset"
    generate_outputs "$conan_bin"
    echo "Restored and verified Phone 16 KiB dependencies"
    rm -rf -- "$download_dir"
    trap - EXIT RETURN
}

export_artifact() {
    local output_dir="${1:-}" conan_bin archive qt_package_dir temp_dir
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
    "$android_root/phone/tests/check-phone-elf-alignment.sh" "$qt_package_dir"
    temp_dir="$(mktemp -d "${TMPDIR:-/tmp}/overte-phone-16k-export.XXXXXXXX")"
    trap 'rm -rf -- "$temp_dir"' RETURN
    "$conan_bin" graph info "$conanfile" -pr:h "$qt_profile" \
        -pr:b "$build_profile" --no-remote --format=json \
        >"$temp_dir/graph.json"
    "$conan_bin" list --graph="$temp_dir/graph.json" --graph-binaries='*' \
        --graph-recipes='*' --format=json >"$temp_dir/packages.json"
    "$conan_bin" cache save --list="$temp_dir/packages.json" --no-source --file="$archive"
    (cd "$output_dir" && sha256sum "$asset") \
        >"$output_dir/${tag}.sha256"
    rm -rf -- "$temp_dir"
    trap - RETURN
    echo "Created $archive and ${tag}.sha256"
}

case "${1:-}" in
    download) download_artifact ;;
    export) export_artifact "${2:-}" ;;
    *) fail "usage: $0 download | export ABSOLUTE_OUTPUT_DIRECTORY" ;;
esac
