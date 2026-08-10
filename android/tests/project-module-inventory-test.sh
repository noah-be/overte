#!/usr/bin/env bash
set -euo pipefail
readonly repository_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
exec python3 "$repository_root/android/tests/project-module-inventory-test.py" "$repository_root"
