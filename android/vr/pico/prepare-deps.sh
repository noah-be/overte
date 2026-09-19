#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Source preparation is read-only. Gradle consumes these same explicit inputs;
# no local rebuild, compatibility archive, or shared runtime override is made.
exec python3 "$script_dir/release/pico-source-inputs.py" --pico-root "$script_dir"
