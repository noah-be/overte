#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly android_root="$(cd -- "$script_dir/../.." && pwd)"
readonly repo_root="$(cd -- "$android_root/.." && pwd)"
readonly self="$script_dir/$(basename -- "${BASH_SOURCE[0]}")"

# Keep this list narrow: it covers Android tablet implementation material
# without scanning unrelated historical or local hand-off files.
declare -a candidates=()
while IFS= read -r -d '' file; do
    candidates+=("$file")
done < <(find \
    "$android_root/common/tests" \
    "$android_root/phone/tests" \
    "$repo_root/scripts/+android_phoneInterface" \
    "$repo_root/scripts/system/+android_phoneInterface" \
    "$repo_root/interface/resources/qml/+android_phoneInterface" \
    -type f -iname '*tablet*' ! -path "$self" -print0 2>/dev/null)

if ((${#candidates[@]} == 0)); then
    printf 'FAIL: no Android tablet implementation or test files were found\n' >&2
    exit 1
fi

# Reject workstation paths, local-network endpoints, and commands containing a
# concrete ADB serial. Documentation may say "adb" or use placeholders.
declare -a forbidden=(
    '(/home/|/Users/)[^ <`"]+/'
    '([0-9]{1,3}[.]){3}[0-9]{1,3}:[0-9]{2,5}'
    'adb[[:space:]]+-s[[:space:]]+[A-Za-z0-9._:-]{6,}'
    'adb[[:space:]]+connect[[:space:]]+([0-9]{1,3}[.]){3}[0-9]{1,3}'
)

for pattern in "${forbidden[@]}"; do
    if grep -EIn -- "$pattern" "${candidates[@]}"; then
        printf 'FAIL: Android tablet files contain private machine or device data\n' >&2
        exit 1
    fi
done

printf 'Android tablet privacy checks passed (%d files checked).\n' "${#candidates[@]}"
