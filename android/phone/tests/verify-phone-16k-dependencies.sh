#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: verify-phone-16k-dependencies.sh [--write-sentinel] <qt-conan-dir> <nonqt-conan-dir> <sentinel>

Verifies the exact Qt and non-Qt Conan packages used by the phone build. The
sentinel contains only a version and a content digest; it never contains host
paths, device identifiers, or device diagnostics.
EOF
}

write_sentinel=false
if [[ ${1:-} == --write-sentinel ]]; then
    write_sentinel=true
    shift
fi
if [[ $# -ne 3 ]]; then
    usage >&2
    exit 2
fi

readonly qt_conan_dir=$1
readonly nonqt_conan_dir=$2
readonly sentinel=$3
readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly alignment_check="$script_dir/check-phone-elf-alignment.sh"
readonly sentinel_version='overte-phone-16k-dependencies-v3'
readonly temp_root="${PHONE_VERIFY_TMPDIR:-$script_dir/../build/verification-tmp}"

lock_timeout="${OVERTE_PHONE_16K_SENTINEL_LOCK_TIMEOUT_SECONDS:-600}"
if [[ ! "$lock_timeout" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    echo "ERROR: invalid Phone dependency sentinel lock timeout: $lock_timeout" >&2
    exit 2
fi
mkdir -p -- "$(dirname -- "$sentinel")"
exec {sentinel_lock_fd}>>"${sentinel}.lock"
lock_mode=-s
$write_sentinel && lock_mode=-x
if ! flock "$lock_mode" -w "$lock_timeout" "$sentinel_lock_fd"; then
    echo "ERROR: timed out waiting for Phone dependency sentinel lock" >&2
    exit 1
fi
if [[ -L "$sentinel" || ( -e "$sentinel" && ! -f "$sentinel" ) ]]; then
    echo "ERROR: Phone dependency sentinel must be a regular non-symlink file" >&2
    exit 2
fi
if $write_sentinel; then
    rm -f -- "$sentinel"
fi

temp_dir=''
sentinel_tmp=''
cleanup() {
    [[ -z "$sentinel_tmp" ]] || rm -f -- "$sentinel_tmp"
    [[ -z "$temp_dir" ]] || rm -rf -- "$temp_dir"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

declare -a generator_specs=(
    "$qt_conan_dir/generators/Qt5-debug-armv8-data.cmake:qt"
    "$nonqt_conan_dir/generators/OpenSSL-debug-armv8-data.cmake:openssl"
    "$nonqt_conan_dir/generators/TBB-debug-armv8-data.cmake:tbb"
    "$nonqt_conan_dir/generators/libnode-debug-armv8-data.cmake:libnode"
    "$nonqt_conan_dir/generators/webrtc-audio-processing-debug-armv8-data.cmake:webrtc-audio-processing"
)

# These patterns mirror preparePhoneConanGenerators in build.gradle. Qt's
# complete generator graph is copied; only these non-Qt graphs overlay it.
declare -a nonqt_generator_patterns=(
    'OpenSSL*' 'module-OpenSSL*' 'FindOpenSSL.cmake' 'TBB*' 'libnode*'
    'webrtc-audio-processing*'
)

# preparePhoneQtRuntime copies these exact files from conanlibs/Debug and
# renames them for Android. Package-folder verification alone is insufficient:
# Conan can leave this staging directory stale after regenerating packages.
declare -a staged_nonqt_libraries=(
    'libcrypto.so.3'
    'libssl.so.3'
)

[[ ! -L "$temp_root" ]] || {
    echo "ERROR: Phone verification temporary directory must not be a symlink" >&2
    exit 2
}
mkdir -p -- "$temp_root"
[[ -d "$temp_root" && -w "$temp_root" ]] || {
    echo "ERROR: Phone verification temporary directory is not writable" >&2
    exit 2
}
temp_dir=$(mktemp -d "$temp_root/overte-phone-16k-ready.XXXXXXXX")
manifest="$temp_dir/manifest"
staged_alignment_dir="$temp_dir/staged-nonqt"
: > "$manifest"
mkdir -- "$staged_alignment_dir"

append_manifest_entry() {
    local kind=$1
    local label=$2
    local root=$3
    local entry=$4
    local relative=${entry#"$root"/}
    if [[ -L "$entry" ]]; then
        printf '%s-symlink %s/%s %s\n' "$kind" "$label" "$relative" \
            "$(readlink -- "$entry")" >> "$manifest"
    else
        printf '%s-file %s/%s %s\n' "$kind" "$label" "$relative" \
            "$(sha256sum "$entry" | cut -d' ' -f1)" >> "$manifest"
    fi
}

append_generator_manifest_entry() {
    local label=$1
    local root=$2
    local entry=$3
    if [[ -L "$entry" ]]; then
        echo "ERROR: Conan generator $label must not be a symlink: $entry" >&2
        return 1
    fi
    append_manifest_entry generator "$label" "$root" "$entry"
}

verify_package_symlinks() {
    local label=$1
    local package_dir=$2
    local package_root
    local link
    local target
    package_root=$(realpath -e -- "$package_dir") || return 1
    while IFS= read -r -d '' link; do
        target=$(realpath -e -- "$link") || {
            echo "ERROR: Conan package $label contains a broken symlink: $link" >&2
            return 1
        }
        case "$target" in
            "$package_root"|"$package_root"/*) ;;
            *)
                echo "ERROR: Conan package $label contains a symlink outside its package: $link" >&2
                return 1
                ;;
        esac
    done < <(find "$package_dir" -type l -print0 | sort -z)
}

qt_generators="$qt_conan_dir/generators"
nonqt_generators="$nonqt_conan_dir/generators"
for generator_dir in "$qt_generators" "$nonqt_generators"; do
    if [[ ! -d "$generator_dir" ]]; then
        echo "ERROR: required Conan generator directory is missing: $generator_dir" >&2
        exit 1
    fi
done
while IFS= read -r -d '' generator_file; do
    append_generator_manifest_entry qt "$qt_generators" "$generator_file"
done < <(find "$qt_generators" \( -type f -o -type l \) \
    -print0 | sort -z)

declare -A selected_nonqt_generators=()
for pattern in "${nonqt_generator_patterns[@]}"; do
    while IFS= read -r -d '' generator_file; do
        selected_nonqt_generators["$generator_file"]=1
    done < <(find "$nonqt_generators" -maxdepth 1 \( -type f -o -type l \) \
        -name "$pattern" -print0)
done
while IFS= read -r generator_file; do
    [[ -n "$generator_file" ]] || continue
    append_generator_manifest_entry nonqt "$nonqt_generators" "$generator_file"
done < <(printf '%s\n' "${!selected_nonqt_generators[@]}" | LC_ALL=C sort)

for spec in "${generator_specs[@]}"; do
    generator=${spec%:*}
    label=${spec##*:}
    if [[ ! -f "$generator" ]]; then
        echo "ERROR: required Conan generator is missing: $generator" >&2
        exit 1
    fi

    package_dir=$(sed -n 's/^set([^ ]*_PACKAGE_FOLDER_DEBUG "\([^"]*\)")$/\1/p' \
        "$generator" | head -n 1)
    if [[ -z "$package_dir" || ! -d "$package_dir" ]]; then
        echo "ERROR: $generator does not identify an existing debug package folder." >&2
        exit 1
    fi
    if ! find "$package_dir" -type f \( -name '*.so' -o -name '*.so.*' \) \
        -print -quit | grep -q .; then
        echo "ERROR: Conan package $label contains no shared libraries: $package_dir" >&2
        exit 1
    fi

    verify_package_symlinks "$label" "$package_dir"
    TMPDIR="$temp_dir" "$alignment_check" "$package_dir"
    while IFS= read -r -d '' library; do
        append_manifest_entry library "$label" "$package_dir" "$library"
    done < <(find "$package_dir" \( -type f -o -type l \) \
        \( -name '*.so' -o -name '*.so.*' \) \
        -print0 | sort -z)
done

nonqt_conanlibs="$nonqt_conan_dir/conanlibs/Debug"
if [[ ! -d "$nonqt_conanlibs" ]]; then
    echo "ERROR: required non-Qt Conan library staging directory is missing: $nonqt_conanlibs" >&2
    exit 1
fi
for library_name in "${staged_nonqt_libraries[@]}"; do
    staged_library="$nonqt_conanlibs/$library_name"
    if [[ ! -f "$staged_library" || -L "$staged_library" ]]; then
        echo "ERROR: required staged non-Qt library is missing or is not a regular file: $staged_library" >&2
        exit 1
    fi
    # Hash and inspect the same private snapshot. Hashing the source and then
    # copying it would allow a concurrent replacement to make the sentinel
    # describe different bytes from those checked for ELF alignment.
    staged_snapshot="$staged_alignment_dir/$library_name"
    cp -- "$staged_library" "$staged_snapshot"
    append_manifest_entry staged-library nonqt "$staged_alignment_dir" "$staged_snapshot"
done
TMPDIR="$temp_dir" "$alignment_check" "$staged_alignment_dir"

digest=$(LC_ALL=C sort "$manifest" | sha256sum | cut -d' ' -f1)
expected="$sentinel_version
$digest"

if $write_sentinel; then
    sentinel_tmp=$(mktemp "$(dirname -- "$sentinel")/.${sentinel##*/}.staging.XXXXXXXX")
    printf '%s\n' "$expected" > "$sentinel_tmp"
    mv -f -- "$sentinel_tmp" "$sentinel"
    sentinel_tmp=''
    echo "Wrote verified 16 KiB dependency sentinel: $sentinel"
elif [[ ! -f "$sentinel" ]] || [[ $(cat -- "$sentinel") != "$expected" ]]; then
    echo "ERROR: 16 KiB dependency sentinel is missing or stale: $sentinel" >&2
    echo "Re-run ./prepare-phone-16k-conan-deps.sh after both dependency builds finish." >&2
    exit 1
else
    echo "The 16 KiB dependency sentinel matches all verified package contents."
fi
