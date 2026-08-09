#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly script_dir
android_root="$(cd -- "$script_dir/../.." && pwd)"
readonly android_root
repo_root="$(cd -- "$android_root/.." && pwd)"
readonly repo_root
readonly tools_root="${OVERTE_STATIC_QUALITY_TOOLS_DIR:-$android_root/build/tools/static-quality}"
readonly lock_file="${tools_root}.lock"
readonly shellcheck="${OVERTE_SHELLCHECK_COMMAND:-$tools_root/bin/shellcheck}"
readonly ruff="${OVERTE_RUFF_COMMAND:-$tools_root/ruff-venv/bin/ruff}"

lock_timeout="${OVERTE_STATIC_QUALITY_LOCK_TIMEOUT_SECONDS:-600}"
if [[ ! "$lock_timeout" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    printf 'FAIL: invalid static quality tool lock timeout: %s\n' "$lock_timeout" >&2
    exit 2
fi
mkdir -p -- "$(dirname -- "$lock_file")"
exec {quality_lock_fd}>>"$lock_file"
if ! flock -s -w "$lock_timeout" "$quality_lock_fd"; then
    printf 'FAIL: timed out waiting for static quality tool lock: %s\n' \
        "$lock_file" >&2
    exit 1
fi

[[ -x "$shellcheck" ]] || { printf 'FAIL: pinned ShellCheck is missing; run tests/quality/install-tools.sh\n' >&2; exit 1; }
[[ -x "$ruff" ]] || { printf 'FAIL: pinned Ruff is missing; run tests/quality/install-tools.sh\n' >&2; exit 1; }
"$shellcheck" --version | grep -Fxq 'version: 0.11.0' || {
    printf 'FAIL: ShellCheck 0.11.0 is required\n' >&2; exit 1;
}
[[ "$("$ruff" --version)" == 'ruff 0.15.22' ]] || {
    printf 'FAIL: Ruff 0.15.22 is required\n' >&2; exit 1;
}

mapfile -t relative_shell_files < <(git -C "$repo_root" ls-files \
    'android/ci/*.sh' \
    'android/device-lock-core.sh' \
    'android/phone-device-lock.sh' \
    'android/phone-build-resource-guard.sh' \
    'android/phone-emulator-test.sh' \
    'android/tests/ci/*.sh' \
    'android/tests/suite/*.sh' \
    'android/tests/reporting/*.sh' \
    'android/tests/docs/*.sh' \
    'android/tests/quality/*.sh')
(( ${#relative_shell_files[@]} > 0 )) || {
    printf 'FAIL: static quality ShellCheck inventory is empty\n' >&2; exit 1;
}
shell_files=()
for relative in "${relative_shell_files[@]}"; do
    shell_files+=("$repo_root/$relative")
done
"$shellcheck" --norc --severity=warning -x -P SCRIPTDIR "${shell_files[@]}"

"$ruff" check --no-cache --select E4,E7,E9,F \
    "$android_root/ci" \
    "$android_root/tests/ci" \
    "$android_root/tests/suite" \
    "$android_root/tests/reporting" \
    "$android_root/tests/docs" \
    "$android_root/tests/mutation" \
    "$android_root/tests/stability"
printf 'Pinned ShellCheck and Ruff quality gates passed\n'
