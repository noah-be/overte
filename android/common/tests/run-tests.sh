#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly script_dir
android_root="$(cd -- "$script_dir/../.." && pwd)"
readonly android_root
repo_root="$(cd -- "$android_root/.." && pwd)"
readonly repo_root

if (( $# == 0 )); then
    printf 'usage: %s TIER [--report-dir PATH] [--list]\n' "${0##*/}" >&2
    exit 2
fi

readonly tier="$1"
shift
report_dir="$android_root/build/test-results/suite"
list=0
while (( $# > 0 )); do
    case "$1" in
        --report-dir)
            (( $# >= 2 )) || { echo 'error: --report-dir requires a path' >&2; exit 2; }
            report_dir="$2"
            shift 2
            ;;
        --list)
            list=1
            shift
            ;;
        *)
            printf 'error: unsupported argument: %s\n' "$1" >&2
            exit 2
            ;;
    esac
done

args=(--profile "android-$tier")
if (( list )); then
    args+=(--list)
else
    args+=(--junit "$report_dir/TEST-android-$tier.xml")
fi
exec python3 "$repo_root/tests/run-tests.py" "${args[@]}"
