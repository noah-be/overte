#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly script_dir
python3 -m unittest discover -s "$script_dir" -p 'test_*.py' -v
exec python3 "$script_dir/validate_ci_contract.py"
