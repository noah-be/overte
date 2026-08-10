#!/usr/bin/env bash
set -euo pipefail

readonly android_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
python3 "$android_root/tests/mutation/test_runner.py"
exec python3 "$android_root/tests/mutation/run_mutations.py" "$@"
