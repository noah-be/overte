#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
source_file="$root/interface/src/Application.cpp"

grep -Eq 'QStandardPaths::writableLocation\(QStandardPaths::CacheLocation\)' "$source_file"
grep -Eq 'filePath\(QStringLiteral\("world-status"\)\)' "$source_file"
grep -Fq 'debug.overte.malloc_trim' "$source_file"
grep -Fq 'mallopt(M_PURGE, 0)' "$source_file"
grep -Fq 'mallopt(M_DECAY_TIME, decay)' "$source_file"
if grep -Fq '/data/user/0/org.overte.pico/cache/world-status' "$source_file"; then
    echo 'world status still uses the Pico package path' >&2
    exit 1
fi
printf 'phone world-status path test passed\n'
