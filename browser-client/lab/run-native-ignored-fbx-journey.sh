#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Require a real graphics context for the production-worker pixel controls.
set -euo pipefail
export OVERTE_LAB_BROWSER_DISPLAY="${DISPLAY:?The FBX pixel fixture requires a display}"
for engine in chromium firefox; do
    OVERTE_LAB_BROWSER="$engine" node --import tsx tests/integration/native-ignored-fbx-pixels.mjs
done
