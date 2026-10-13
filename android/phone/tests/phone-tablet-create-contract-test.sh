#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../../.." && pwd)"
defaults="$repo_root/scripts/+android_phoneInterface/defaultScripts.js"

# Native Create is shared Main functionality, executed by the Android contract
# runner. Keep its undo state in a separate engine from the service bootstrap.
grep -Eq 'Script[.]load\("/~/system/create/edit[.]js"\)' "$defaults"
if grep -Eq 'Script[.]include\([^)]*system/create/edit[.]js' "$defaults"; then
    printf 'FAIL: Create shares the service-bootstrap engine\n' >&2
    exit 1
fi

# Execute the shipped editor/bridge: creation, conversion, undo/redo, permissions,
# stale callbacks and shutdown must work. Native OS/device boundaries remain
# explicit in these existing Main host fixtures; this is not device acceptance.
node --test \
    "$repo_root/tests/javascript/test/mobile-create.editor.test.js" \
    "$repo_root/tests/javascript/test/mobile-create.bridge.test.js"
printf 'Android native Create behavior contract passed.\n'
