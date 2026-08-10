#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly script_dir
exec python3 -m unittest discover -s "$script_dir" -p 'test_*.py' -v
