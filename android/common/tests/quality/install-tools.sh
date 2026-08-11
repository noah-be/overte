#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly script_dir
android_root="$(cd -- "$script_dir/../../.." && pwd)"
readonly android_root
readonly tools_root="${OVERTE_STATIC_QUALITY_TOOLS_DIR:-$android_root/build/tools/static-quality}"
readonly lock_file="${tools_root}.lock"
readonly shellcheck_version=0.11.0
readonly shellcheck_sha256=8c3be12b05d5c177a04c29e3c78ce89ac86f1595681cab149b65b97c4e227198
readonly shellcheck_url="https://github.com/koalaman/shellcheck/releases/download/v${shellcheck_version}/shellcheck-v${shellcheck_version}.linux.x86_64.tar.xz"

lock_timeout="${OVERTE_STATIC_QUALITY_LOCK_TIMEOUT_SECONDS:-600}"
if [[ ! "$lock_timeout" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    printf 'FAIL: invalid static quality tool lock timeout: %s\n' "$lock_timeout" >&2
    exit 2
fi
mkdir -p -- "$(dirname -- "$lock_file")"
exec {quality_lock_fd}>>"$lock_file"
if ! flock -x -w "$lock_timeout" "$quality_lock_fd"; then
    printf 'FAIL: timed out waiting for static quality tool lock: %s\n' \
        "$lock_file" >&2
    exit 1
fi

case "$(uname -s):$(uname -m)" in
    Linux:x86_64) ;;
    *) printf 'FAIL: pinned static quality tools require Linux x86_64\n' >&2; exit 1 ;;
esac

mkdir -p -- "$tools_root/bin"
temporary="$(mktemp -d "${TMPDIR:-/tmp}/overte-static-quality-install.XXXXXXXX")"
cleanup() {
    rm -rf -- "$temporary"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
curl --fail --silent --show-error --location --retry 4 --retry-all-errors \
    --connect-timeout 20 --max-time 300 "$shellcheck_url" --output "$temporary/shellcheck.tar.xz"
printf '%s  %s\n' "$shellcheck_sha256" "$temporary/shellcheck.tar.xz" | \
    sha256sum --check --status
tar -xJf "$temporary/shellcheck.tar.xz" -C "$temporary"
install -m 755 "$temporary/shellcheck-v${shellcheck_version}/shellcheck" \
    "$tools_root/bin/shellcheck"

python3 -m venv "$tools_root/ruff-venv"
"$tools_root/ruff-venv/bin/pip" install --disable-pip-version-check \
    --require-hashes --only-binary=:all: --no-deps -r "$script_dir/requirements.txt"
"$tools_root/bin/shellcheck" --version | grep -Fxq "version: $shellcheck_version"
[[ "$("$tools_root/ruff-venv/bin/ruff" --version)" == 'ruff 0.15.22' ]]
