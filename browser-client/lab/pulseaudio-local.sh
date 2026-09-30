#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Use the uninstalled laboratory RPMs without changing the desktop audio server.
set -euo pipefail
lab_repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
lab_tools="$lab_repo_root/build/browser-lab/host-tools"
export LD_LIBRARY_PATH="$lab_tools/usr/lib64:$lab_tools/usr/lib64/pulseaudio:$lab_tools/usr/lib64/pulseaudio/modules${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$lab_tools/usr/bin/pulseaudio" --dl-search-path="$lab_tools/usr/lib64/pulseaudio/modules" "$@"
