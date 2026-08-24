#!/bin/bash

set -euo pipefail

package_dir="$(cd "$(dirname "$0")" && pwd)"
app="$package_dir/Overte.app"
exec "$app/Contents/MacOS/Overte" \
    --no-updater \
    --no-launcher \
    --suppress-settings-reset \
    --testScript "file://$package_dir/qemu-low-power.js" \
    "$@"
