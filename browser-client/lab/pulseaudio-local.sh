#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Select the prepared lab's verified audio tools, never the desktop audio daemon.
set -euo pipefail
lab_repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
lab_runtime_root="${OVERTE_LAB_ROOT:-$lab_repo_root/build/browser-lab}"
exec python3 "$lab_repo_root/browser-client/lab/host_tools.py" exec-pulse --root "$lab_runtime_root" -- "$@"
