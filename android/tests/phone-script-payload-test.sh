#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly android_root="$(cd -- "$script_dir/.." && pwd)"
readonly repo_root="$(cd -- "$android_root/.." && pwd)"
readonly gradle="$android_root/apps/phoneInterface/build.gradle"
readonly defaults="$repo_root/scripts/+android_phoneInterface/defaultScripts.js"

grep -Eq "exclude 'simplifiedUI/[*][*]'" "$gradle"
grep -Eq "exclude 'simplifiedUIBootstrapper[.]js'" "$gradle"
for excluded in developer tutorials communityScripts; do
    grep -Eq "exclude '$excluded/[*][*]'" "$gradle"
done

if grep -Eq 'simplifiedUI|simplifiedUIBootstrapper' "$defaults"; then
    echo 'FAIL: phone defaults depend on the excluded Simplified UI payload' >&2
    exit 1
fi
if grep -Eq 'developer/|tutorials/|communityScripts/' "$defaults"; then
    echo 'FAIL: phone defaults depend on an excluded example or desktop app' >&2
    exit 1
fi

for required in \
        system/progress.js \
        system/+android_interface/touchscreenvirtualpad.js \
        system/+android_phoneInterface/mobileActionBar.js \
        system/makeUserConnection.js \
        system/+android_interface/androidControls.js; do
    test -f "$repo_root/scripts/$required" || {
        echo "FAIL: required phone script is missing: $required" >&2
        exit 1
    }
done

python3 - \
        "$repo_root/scripts/simplifiedUI" \
        "$repo_root/scripts/developer" \
        "$repo_root/scripts/tutorials" \
        "$repo_root/scripts/communityScripts" <<'PY'
import pathlib
import sys

roots = [pathlib.Path(value) for value in sys.argv[1:]]
files = [path for root in roots for path in root.rglob('*') if path.is_file()]
raw_bytes = sum(path.stat().st_size for path in files)
if raw_bytes < 90_000_000:
    raise SystemExit('FAIL: excluded script fixtures no longer prove a material payload saving')
print(f'Phone script payload checks passed ({len(files)} files, {raw_bytes} raw bytes excluded).')
PY
