#!/usr/bin/env bash

set -uo pipefail

readonly REQUIRED_ALIGNMENT=$((0x4000))
temp_dir=""

cleanup() {
    if [[ -n "$temp_dir" && -d "$temp_dir" ]]; then
        rm -rf -- "$temp_dir"
    fi
}
trap cleanup EXIT INT TERM

usage() {
    cat <<'EOF'
Usage: ./tests/check-phone-elf-alignment.sh <apk-or-directory>

Checks every packaged or staged .so/.so.* file and fails if any ELF LOAD
segment has an alignment below 0x4000 (16 KiB). The input is never modified.
EOF
}

if [[ $# -ne 1 ]]; then
    usage >&2
    exit 2
fi

input_path=$1
scan_root=""

if [[ -d "$input_path" ]]; then
    scan_root=$input_path
elif [[ -f "$input_path" ]]; then
    if ! command -v unzip >/dev/null 2>&1; then
        echo "ERROR: unzip is required to inspect an APK." >&2
        exit 2
    fi
    temp_dir=$(mktemp -d "${TMPDIR:-/tmp}/overte-phone-elf.XXXXXXXX") || {
        echo "ERROR: could not create a temporary directory." >&2
        exit 2
    }
    if ! unzip -qq "$input_path" -d "$temp_dir"; then
        echo "ERROR: could not extract Android package" >&2
        exit 2
    fi
    scan_root=$temp_dir
else
    echo "ERROR: input is neither an Android package nor a directory" >&2
    usage >&2
    exit 2
fi

scan_root_canonical=$(realpath -e -- "$scan_root") || {
    echo "ERROR: could not resolve package scan root" >&2
    exit 2
}

readelf_tool=""
for candidate in llvm-readelf readelf; do
    if command -v "$candidate" >/dev/null 2>&1; then
        readelf_tool=$(command -v "$candidate")
        break
    fi
done

if [[ -z "$readelf_tool" && -n "${ANDROID_NDK_HOME:-}" && \
      -x "${ANDROID_NDK_HOME}/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf" ]]; then
    readelf_tool="${ANDROID_NDK_HOME}/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf"
fi

if [[ -z "$readelf_tool" ]]; then
    echo "ERROR: llvm-readelf or readelf was not found in PATH." >&2
    exit 2
fi

library_count=0
segment_count=0
failed_library_count=0
inspection_error_count=0

while IFS= read -r -d '' library; do
    ((library_count += 1))
    display_path=${library#"$scan_root"/}
    inspected_library=$library
    if [[ -L "$library" ]]; then
        inspected_library=$(realpath -e -- "$library") || {
            echo "ERROR  $display_path: shared-library symlink has no existing target" >&2
            ((inspection_error_count += 1))
            continue
        }
        case "$inspected_library" in
            "$scan_root_canonical"/*) ;;
            *)
                echo "ERROR  $display_path: shared-library symlink escapes the package directory" >&2
                ((inspection_error_count += 1))
                continue
                ;;
        esac
    fi
    program_headers=$($readelf_tool -lW -- "$inspected_library" 2>&1)
    readelf_status=$?
    if (( readelf_status != 0 )); then
        echo "ERROR  $display_path: readelf failed" >&2
        ((inspection_error_count += 1))
        continue
    fi

    library_failed=0
    library_segments=0
    while IFS= read -r alignment; do
        [[ -z "$alignment" ]] && continue
        ((library_segments += 1))
        ((segment_count += 1))
        if [[ ! "$alignment" =~ ^0[xX][0-9a-fA-F]+$ ]]; then
            echo "ERROR  $display_path: unrecognized LOAD alignment '$alignment'" >&2
            ((inspection_error_count += 1))
            library_failed=2
            break
        fi
        alignment_value=$((alignment))
        if (( alignment_value < REQUIRED_ALIGNMENT )); then
            printf 'FAIL   %s: LOAD alignment %s is below 0x4000\n' \
                "$display_path" "$alignment"
            library_failed=1
        fi
    done < <(awk '$1 == "LOAD" { print $NF }' <<<"$program_headers")

    if (( library_segments == 0 && library_failed == 0 )); then
        echo "ERROR  $display_path: no ELF LOAD segments found" >&2
        ((inspection_error_count += 1))
        continue
    fi
    if (( library_failed == 1 )); then
        ((failed_library_count += 1))
    elif (( library_failed == 0 )); then
        printf 'PASS   %s (%d LOAD segments)\n' "$display_path" "$library_segments"
    fi
done < <(find "$scan_root" \( -type f -o -type l \) \
    \( -name '*.so' -o -name '*.so.*' \) \
    -print0 | sort -z)

if (( library_count == 0 )); then
    echo "ERROR: package contains no inspectable shared libraries" >&2
    exit 2
fi

printf '\nSummary: %d libraries, %d LOAD segments, %d failed libraries, %d inspection errors\n' \
    "$library_count" "$segment_count" "$failed_library_count" "$inspection_error_count"

if (( failed_library_count > 0 || inspection_error_count > 0 )); then
    exit 1
fi

echo "All ELF LOAD segments meet the 0x4000 (16 KiB) alignment requirement."
