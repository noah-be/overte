#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly script_dir
android_root="$(cd -- "$script_dir/../../.." && pwd)"
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

[[ -x "$shellcheck" ]] || { printf 'FAIL: pinned ShellCheck is missing; run android/common/tests/quality/install-tools.sh\n' >&2; exit 1; }
[[ -x "$ruff" ]] || { printf 'FAIL: pinned Ruff is missing; run android/common/tests/quality/install-tools.sh\n' >&2; exit 1; }
"$shellcheck" --version | grep -Fxq 'version: 0.11.0' || {
    printf 'FAIL: ShellCheck 0.11.0 is required\n' >&2; exit 1;
}
[[ "$("$ruff" --version)" == 'ruff 0.15.22' ]] || {
    printf 'FAIL: Ruff 0.15.22 is required\n' >&2; exit 1;
}

mapfile -t relative_shell_files < <(git -C "$repo_root" ls-files \
    'android/phone/ci/*.sh' \
    'android/vr/pico/ci/*.sh' \
    'android/common/scripts/device-lock-core.sh' \
    'android/phone/phone-device-lock.sh' \
    'android/phone/phone-build-resource-guard.sh' \
    'android/phone/phone-emulator-test.sh' \
    'android/common/tests/ci/*.sh' \
    'android/common/tests/suite/*.sh' \
    'android/common/tests/reporting/*.sh' \
    'android/common/tests/docs/*.sh' \
    'android/common/tests/quality/*.sh')
(( ${#relative_shell_files[@]} > 0 )) || {
    printf 'FAIL: static quality ShellCheck inventory is empty\n' >&2; exit 1;
}
shell_files=()
for relative in "${relative_shell_files[@]}"; do
    shell_files+=("$repo_root/$relative")
done
"$shellcheck" --norc --severity=warning -x -P SCRIPTDIR "${shell_files[@]}"

"$ruff" check --no-cache --select E4,E7,E9,F \
    "$android_root/phone/ci" \
    "$android_root/vr/pico/ci" \
    "$android_root/common/tests/ci" \
    "$android_root/common/tests/suite" \
    "$android_root/common/tests/reporting" \
    "$android_root/common/tests/docs" \
    "$android_root/common/tests/mutation" \
    "$android_root/common/tests/stability"
printf 'Pinned ShellCheck and Ruff quality gates passed\n'
