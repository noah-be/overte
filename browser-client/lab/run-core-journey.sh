#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run from the repository root beneath the caller's private display owner.
set -euo pipefail
export OVERTE_LAB_BROWSER_DISPLAY="${DISPLAY:?The actual browser journey requires a display}"
exec node browser-client/tests/integration/real-session.mjs
