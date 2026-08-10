#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repository_root="$(cd -- "$script_dir/../.." && pwd)"

declare -a scripts=()
if (( $# > 0 )); then
    scripts=("$@")
else
    mapfile -d '' scripts < <(
        git -C "$repository_root" ls-files -z -- 'android/*.sh' 'android/**/*.sh'
    )
fi

if (( ${#scripts[@]} == 0 )); then
    printf 'FAIL: no Android Bash scripts were selected\n' >&2
    exit 1
fi

failures=0
for script in "${scripts[@]}"; do
    if [[ "$script" = /* ]]; then
        candidate="$script"
    else
        candidate="$repository_root/$script"
    fi
    if [[ ! -f "$candidate" ]]; then
        printf 'FAIL: shell syntax input is not a regular file: %s\n' "$script" >&2
        failures=$((failures + 1))
        continue
    fi
    if ! bash -n "$candidate"; then
        printf 'FAIL: invalid Bash syntax: %s\n' "$script" >&2
        failures=$((failures + 1))
    fi
done

if (( failures > 0 )); then
    printf 'Shell syntax contract failed for %d of %d scripts\n' \
        "$failures" "${#scripts[@]}" >&2
    exit 1
fi

printf 'Android shell syntax contract passed for %d scripts\n' "${#scripts[@]}"
