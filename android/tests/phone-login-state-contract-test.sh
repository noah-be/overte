#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
temporary_dir="$(mktemp -d "${TMPDIR:-/tmp}/overte-phone-login-contract.XXXXXXXX")"
trap 'rm -rf -- "$temporary_dir"' EXIT

"${CXX:-c++}" \
    -std=c++11 \
    -Wall \
    -Wextra \
    -Werror \
    -I"$repo_root/interface/src/ui" \
    "$script_dir/phone-login-state-contract-test.cpp" \
    -o "$temporary_dir/phone-login-state-contract-test"

"$temporary_dir/phone-login-state-contract-test"
printf 'Phone login asynchronous state contract passed.\n'
