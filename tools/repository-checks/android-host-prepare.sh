#!/usr/bin/env bash
# Trusted host tools only. Never execute candidate installers or prepare an APK.
set -euo pipefail
[[ $# == 1 ]] || { printf 'Expected an external Android host virtualenv path\n' >&2; exit 2; }
android_host_venv="$1"
python3 -m venv "$android_host_venv"
"$android_host_venv/bin/python" -m pip install --disable-pip-version-check \
    --retries 4 --timeout 30 gcovr==8.4
android_quality_root="$android_host_venv/overte-static-quality"
mkdir -p "$android_quality_root/bin"
python3 -m venv "$android_quality_root/ruff-venv"
printf '%s\n' 'ruff==0.15.22 --hash=sha256:365523eb91d9224e1bcb03b022fbf0facb8f9e23792a2c53d9d4b3924bdbdebb' \
    > "$android_quality_root/requirements.txt"
"$android_quality_root/ruff-venv/bin/python" -m pip install --disable-pip-version-check \
    --require-hashes --only-binary=:all: --no-deps -r "$android_quality_root/requirements.txt"
android_quality_temporary="$(mktemp -d)"
trap 'rm -rf -- "$android_quality_temporary"' EXIT
curl --fail --silent --show-error --location --retry 4 --retry-all-errors \
    --connect-timeout 20 --max-time 300 \
    https://github.com/koalaman/shellcheck/releases/download/v0.11.0/shellcheck-v0.11.0.linux.x86_64.tar.xz \
    --output "$android_quality_temporary/shellcheck.tar.xz"
printf '%s  %s\n' 8c3be12b05d5c177a04c29e3c78ce89ac86f1595681cab149b65b97c4e227198 \
    "$android_quality_temporary/shellcheck.tar.xz" | sha256sum --check --status
tar -xJf "$android_quality_temporary/shellcheck.tar.xz" -C "$android_quality_temporary"
install -m 755 "$android_quality_temporary/shellcheck-v0.11.0/shellcheck" "$android_quality_root/bin/shellcheck"
