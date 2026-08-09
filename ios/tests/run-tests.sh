#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 "$script_dir/port-contract-test.py"
bash -n "$script_dir/../build-ios.sh"
cmake -P "$script_dir/qt-compat-test.cmake"
cmake -P "$script_dir/find-moltenvk-test.cmake"
