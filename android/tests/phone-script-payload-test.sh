#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly android_root="$(cd -- "$script_dir/.." && pwd)"
readonly repo_root="$(cd -- "$android_root/.." && pwd)"
readonly gradle="$android_root/apps/phoneInterface/build.gradle"
readonly defaults="$repo_root/scripts/+android_phoneInterface/defaultScripts.js"

grep -Eq "exclude 'simplifiedUI/[*][*]'" "$gradle"
grep -Eq "exclude 'simplifiedUIBootstrapper[.]js'" "$gradle"

if grep -Eq 'simplifiedUI|simplifiedUIBootstrapper' "$defaults"; then
    echo 'FAIL: phone defaults depend on the excluded Simplified UI payload' >&2
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

python3 - "$repo_root/scripts/simplifiedUI" <<'PY'
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
files = [path for path in root.rglob('*') if path.is_file()]
raw_bytes = sum(path.stat().st_size for path in files)
if raw_bytes < 50_000_000:
    raise SystemExit('FAIL: Simplified UI fixture no longer proves a material payload saving')
print(f'Phone script payload checks passed ({len(files)} files, {raw_bytes} raw bytes excluded).')
PY
