#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${SCCACHE_PATH:?SCCACHE_PATH must name the pinned sccache executable}"
[[ -x "$SCCACHE_PATH" ]] || {
    echo "configured sccache launcher is not executable" >&2
    exit 127
}

# The watchdog receives the real compiler as argv[0] and inserts the pinned
# sccache executable exactly once.  Passing SCCACHE_PATH here as the command
# would produce the recursive chain `sccache sccache clang ...`.
exec "$script_dir/compiler-watchdog.py" -- "$@"
