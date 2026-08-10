#!/usr/bin/env bash
set -euo pipefail

ANDROID_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
while IFS= read -r -d '' script; do
    bash -n "$script"
done < <(find "$ANDROID_DIR" -maxdepth 2 -type f -name '*.sh' -print0)
echo "PASS Pico shell syntax"
