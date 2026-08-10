#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
portal="$repo_root/scripts/system/places/portal.js"

node --check "$portal"
grep -Fq 'try {' "$portal"
grep -Fq 'function validPortalData(data, dimensions)' "$portal"
grep -Fq 'if (!portalReady || teleportTimer !== null)' "$portal"
grep -Fq 'Script.clearTimeout(teleportTimer)' "$portal"
node "$script_dir/phone-tablet-portal-lifecycle-test.js"
