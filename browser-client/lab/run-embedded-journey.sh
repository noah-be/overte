#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run from the browser package beneath an owned real graphics display.
set -euo pipefail
export OVERTE_LAB_BROWSER_DISPLAY="${DISPLAY:?The embedded World fixture requires a display}"
for engine in chromium firefox; do
    OVERTE_LAB_BROWSER="$engine" node tests/integration/embedded-world.mjs
done
