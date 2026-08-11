#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly android_root="$(cd -- "$script_dir/../.." && pwd)"
readonly fixture="$(mktemp -d "${TMPDIR:-/tmp}/overte-phone-qt-fallback.XXXXXXXX")"
trap 'rm -rf -- "$fixture"' EXIT INT TERM

source "$android_root/common/scripts/with-temporary-git-patch.sh"

mkdir -p "$fixture/repository"
git -C "$fixture/repository" init -q
git -C "$fixture/repository" config user.email test@example.invalid
git -C "$fixture/repository" config user.name 'Phone fallback test'
printf 'before\n' >"$fixture/repository/value.txt"
git -C "$fixture/repository" add value.txt
git -C "$fixture/repository" commit -qm base
printf 'during\n' >"$fixture/repository/value.txt"
git -C "$fixture/repository" diff --binary >"$fixture/change.patch"
git -C "$fixture/repository" checkout -q -- value.txt

assert_patched() {
    [[ "$(cat "$fixture/repository/value.txt")" == during ]]
}

fail_while_patched() {
    assert_patched
    return 19
}

interrupt_while_patched() {
    assert_patched
    kill -TERM "$BASHPID"
}

with_temporary_git_patch "$fixture/change.patch" "$fixture/repository" assert_patched
[[ "$(cat "$fixture/repository/value.txt")" == before ]]
[[ -z "$(git -C "$fixture/repository" status --short)" ]]

set +e
with_temporary_git_patch "$fixture/change.patch" "$fixture/repository" fail_while_patched
status=$?
set -e
[[ $status -eq 19 ]]
[[ "$(cat "$fixture/repository/value.txt")" == before ]]
[[ -z "$(git -C "$fixture/repository" status --short)" ]]

set +e
with_temporary_git_patch "$fixture/change.patch" "$fixture/repository" \
    interrupt_while_patched >/dev/null 2>&1
status=$?
set -e
[[ $status -ne 0 ]]
[[ "$(cat "$fixture/repository/value.txt")" == before ]]
[[ -z "$(git -C "$fixture/repository" status --short)" ]]

git -C "$fixture/repository" apply "$fixture/change.patch"
with_temporary_git_patch "$fixture/change.patch" "$fixture/repository" assert_patched
[[ "$(cat "$fixture/repository/value.txt")" == before ]]
[[ -z "$(git -C "$fixture/repository" status --short)" ]]

printf 'not a patch\n' >"$fixture/invalid.patch"
set +e
with_temporary_git_patch "$fixture/invalid.patch" "$fixture/repository" assert_patched \
    >/dev/null 2>&1
status=$?
set -e
[[ $status -ne 0 ]]
[[ "$(cat "$fixture/repository/value.txt")" == before ]]

printf 'Temporary Phone Qt fallback patch checks passed.\n'
