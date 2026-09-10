#!/usr/bin/env bash
# Read-only Shared SH-002 evidence join; not build/scanner/producer acceptance.
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "$script_dir/../../../.." && pwd)
exec python3 "$repo_root/tests/device/schema/android_build_evidence.py" "$@"
