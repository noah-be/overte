#!/usr/bin/env bash
set -euo pipefail
readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 -m unittest "$android_root/tests/stability/test_stability.py"
exec python3 "$android_root/tests/stability/run-order-isolation-audit.py"
