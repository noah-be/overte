#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly android_root="$(cd -- "$script_dir/.." && pwd)"
readonly repo_root="$(cd -- "$android_root/.." && pwd)"
readonly gradle="$android_root/apps/phoneInterface/build.gradle"
readonly defaults="$repo_root/scripts/+android_phoneInterface/defaultScripts.js"
readonly progress="$repo_root/scripts/system/progress.js"

grep -Fq "variant.mergeAssets.inputs.file(project.file('build.gradle'))" "$gradle"
python3 - "$gradle" <<'PY'
import pathlib
import re
import sys

source = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
scripts_stage = re.search(
    r"project[.]sync\s*\{\s*from new File\(projectDir, '../../../scripts'\)(.*?)\n\s*\}",
    source,
    re.S,
)
if not scripts_stage:
    raise SystemExit('FAIL: phone scripts are not staged with stale-output cleanup')
if "into new File(mergedAssetsDir, 'scripts')" not in scripts_stage.group(1):
    raise SystemExit('FAIL: phone script sync no longer targets merged scripts')
PY

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
if grep -Eq 'makeUserConnection' "$defaults"; then
    echo 'FAIL: touchscreen-only phone defaults start the VR handshake service' >&2
    exit 1
fi
for excluded in \
        system/makeUserConnection.js \
        system/assets/images/Bokeh-Particle.png \
        system/assets/sounds/4beat_sweep.wav \
        system/assets/sounds/3rdbeat_success_bell.wav; do
    grep -Fq "exclude '$excluded'" "$gradle"
done

for excluded in \
        system/voxels.js \
        system/assets/images/textures/dirt.jpeg \
        system/assets/images/textures/grass.png; do
    grep -Fq "exclude '$excluded'" "$gradle"
done
grep -Fq 'assets/images/textures/dirt.jpeg' "$repo_root/scripts/system/voxels.js"
grep -Fq 'assets/images/textures/grass.png' "$repo_root/scripts/system/voxels.js"
if rg -l --glob '*.js' 'assets/images/textures/(dirt[.]jpeg|grass[.]png)' \
        "$repo_root/scripts" | grep -Fvqx "$repo_root/scripts/system/voxels.js"; then
    echo 'FAIL: excluded voxel texture gained another script consumer' >&2
    exit 1
fi

for required in \
        system/progress.js \
        system/+android_interface/touchscreenvirtualpad.js \
        system/+android_phoneInterface/mobileActionBar.js \
        system/+android_phoneInterface/mobileTabletApps.js \
        system/+android_interface/androidControls.js; do
    test -f "$repo_root/scripts/$required" || {
        echo "FAIL: required phone script is missing: $required" >&2
        exit 1
    }
done

for required_tablet_app in \
        system/bubble.js \
        system/pal.js \
        system/avatarapp.js \
        system/places/places.js \
        system/quickGoto.js \
        system/create/edit.js; do
    grep -Fq "$required_tablet_app" "$defaults" || {
        echo "FAIL: Pico-compatible tablet app is not enabled: $required_tablet_app" >&2
        exit 1
    }
done

grep -Eq '^var ANDROID_PHONE_INTERFACE = true;' "$defaults"
grep -Eq 'IS_ANDROID_PHONE = typeof ANDROID_PHONE_INTERFACE.*ANDROID_PHONE_INTERFACE' "$progress"
grep -Eq 'ACTIVE_UPDATE_INTERVAL = IS_ANDROID_PHONE [?] 1000 / 30 : 1000 / 60' "$progress"
grep -Eq 'IDLE_PHONE_UPDATE_INTERVAL = 250' "$progress"
grep -Fq 'setUpdateInterval(ACTIVE_UPDATE_INTERVAL);' "$progress"
grep -Fq 'setUpdateInterval(IS_ANDROID_PHONE ? IDLE_PHONE_UPDATE_INTERVAL : ACTIVE_UPDATE_INTERVAL);' "$progress"
grep -Fq ': IDLE_PHONE_UPDATE_INTERVAL);' "$progress"
if grep -Fq 'Script.setInterval(update, 1000 / 60);' "$progress"; then
    echo 'FAIL: phone progress indicator still unconditionally updates at 60 Hz' >&2
    exit 1
fi

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
