#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly android_root="$(cd -- "$script_dir/../.." && pwd)"
readonly repo_root="$(cd -- "$android_root/.." && pwd)"
readonly gradle="$android_root/phone/apps/phoneInterface/build.gradle"
readonly defaults="$repo_root/scripts/+android_phoneInterface/defaultScripts.js"
readonly progress="$repo_root/scripts/system/progress.js"
readonly apk_checker="$android_root/phone/tests/check-phone-apk-contents.py"

grep -Fq "variant.mergeAssets.inputs.file(project.file('build.gradle'))" "$gradle"
python3 - "$gradle" <<'PY'
import pathlib
import re
import sys

source = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
scripts_stage = re.search(
    r"project[.]sync\s*\{\s*from new File\(projectDir, '../../../../scripts'\)(.*?)\n\s*\}",
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
for excluded in developer tutorials; do
    grep -Eq "exclude '$excluded/[*][*]'" "$gradle"
done

if grep -Eq 'simplifiedUI|simplifiedUIBootstrapper' "$defaults"; then
    echo 'FAIL: phone defaults depend on the excluded Simplified UI payload' >&2
    exit 1
fi
if grep -Eq 'developer/|tutorials/' "$defaults"; then
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
if grep -REl --include='*.js' 'assets/images/textures/(dirt[.]jpeg|grass[.]png)' \
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
        system/quickGoto.js; do
    grep -Fq "$required_tablet_app" "$defaults" || {
        echo "FAIL: Pico-compatible tablet app is not enabled: $required_tablet_app" >&2
        exit 1
    }
done

grep -Fq 'Script.load("/~/system/create/edit.js");' "$defaults"
grep -Fq 'Script.load("/~/system/snapshot.js");' "$defaults"

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

python3 - "$defaults" "$apk_checker" "$repo_root/scripts" "$gradle" <<'PY'
import importlib.util
import pathlib
import re
import sys

defaults_path = pathlib.Path(sys.argv[1])
checker_path = pathlib.Path(sys.argv[2])
scripts_root = pathlib.Path(sys.argv[3])
source = defaults_path.read_text(encoding="utf-8")
match = re.search(r"PHONE_DEFAULT_SCRIPTS\s*=\s*\[(.*?)\];", source, re.S)
if not match:
    raise SystemExit("FAIL: could not parse PHONE_DEFAULT_SCRIPTS")
startup_scripts = set(re.findall(r'[\"\']([^\"\']+[.]js)[\"\']', match.group(1)))
startup_scripts.add("+android_phoneInterface/defaultScripts.js")
startup_scripts.add("system/+android_interface/androidControls.js")
startup_scripts.update(re.findall(r'Script[.]load\("/~/([^"\n]+)"\)', source))
expected_cached = {"scripts/" + entry for entry in startup_scripts}

spec = importlib.util.spec_from_file_location("phone_apk_contents_sync", checker_path)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
gradle_source = pathlib.Path(sys.argv[4]).read_text(encoding="utf-8")
community_list = re.search(r"def phoneCommunityRuntimeAssets = \[(.*?)\] as Set", gradle_source, re.S)
if not community_list:
    raise SystemExit("FAIL: Phone packager has no explicit Chat runtime inputs")
packaged_community = set(re.findall(r"'([^']+)'", community_list.group(1)))
if packaged_community != checker.PHONE_COMMUNITY_RUNTIME_ASSETS:
    raise SystemExit("FAIL: Phone Chat packager/APK runtime asset drift")
if "exclude 'communityScripts/**'" in gradle_source:
    raise SystemExit("FAIL: Phone packager still excludes the required Chat runtime")
for expression in (
        "details.path.startsWith('communityScripts/') &&",
        "!phoneCommunityRuntimeAssets.contains(details.path) &&",
        "!phoneCommunityRuntimeAssets.any { it.startsWith(details.path + '/') }"):
    if expression not in gradle_source:
        raise SystemExit("FAIL: Phone packager does not preserve the exact community exclusion")
# Derive the Chat closure from actual shipped resolvePath calls, QML imports,
# static sources and both variants of its dynamic navigation-icon sources.
queue = [entry for entry in startup_scripts if entry.startswith("communityScripts/")]
reachable = set()
while queue:
    entry = queue.pop()
    if entry in reachable:
        continue
    reachable.add(entry)
    path = scripts_root / entry
    if path.suffix not in {".js", ".qml"}:
        continue
    text = path.read_text(encoding="utf-8")
    references = re.findall(r"Script[.]resolvePath\(\s*[\"']([^\"']+)[\"']", text)
    if path.suffix == ".qml":
        references += re.findall(r"source:\s*[\"']([^\"']+)[\"'](?!\s*\+)", text)
        references += re.findall(r"import\s+[\"']([^\"']+)[\"']", text)
        for line in text.splitlines():
            dynamic = re.search(r"source:\s*[\"']([^\"']+/)[\"']\s*\+", line)
            if dynamic:
                references += [dynamic.group(1) + name for name in
                               re.findall(r"[\"']([^\"']+[.]png)[\"']", line)]
    for reference in references:
        if ":" in reference:
            continue
        dependency = (path.parent / reference).resolve()
        if not dependency.is_relative_to(scripts_root.resolve()):
            raise SystemExit("FAIL: Chat runtime dependency escapes the scripts root")
        dependencies = sorted(dependency.glob("*.qml")) if dependency.is_dir() else [dependency]
        for child in dependencies:
            if not child.is_file():
                raise SystemExit(f"FAIL: Chat runtime dependency is missing: {reference}")
            queue.append(child.relative_to(scripts_root).as_posix())
if reachable != packaged_community:
    raise SystemExit(f"FAIL: Chat runtime closure drift; missing={sorted(reachable - packaged_community)}, "
                     f"unreachable={sorted(packaged_community - reachable)}")
print(f"Phone Chat runtime closure verified ({len(reachable)} real JS/QML/image/audio inputs).")
expected_cached.update("scripts/" + entry for entry in packaged_community)
missing_community = sorted(path for path in packaged_community if not (scripts_root / path).is_file())
if missing_community:
    raise SystemExit(f"FAIL: Phone Chat runtime inputs missing: {missing_community}")
# Dynamic QML icon pairs, imported ChatMessage, and native notification sounds
# are all physical cache requirements, not only the three engine entrypoints.
actual_cached = {
    entry for entry in checker.REQUIRED_CACHED_ASSETS if entry.startswith("scripts/")
}
if actual_cached != expected_cached:
    missing = sorted(expected_cached - actual_cached)
    stale = sorted(actual_cached - expected_cached)
    raise SystemExit(f"FAIL: APK/default startup script drift; missing={missing}, stale={stale}")
missing_sources = sorted(
    entry for entry in startup_scripts if not (scripts_root / entry).is_file()
)
if missing_sources:
    raise SystemExit(f"FAIL: Phone default startup sources are missing: {missing_sources}")
print(f"Phone APK/default startup scripts are synchronized ({len(startup_scripts)} scripts).")
PY

python3 - \
        "$repo_root/scripts/simplifiedUI" \
        "$repo_root/scripts/developer" \
        "$repo_root/scripts/tutorials" \
        "$repo_root/scripts/communityScripts" "$apk_checker" <<'PY'
import pathlib
import runpy
import sys

roots = [pathlib.Path(value) for value in sys.argv[1:-1]]
kept = runpy.run_path(sys.argv[-1])["PHONE_COMMUNITY_RUNTIME_ASSETS"]
scripts_root = roots[0].parent
files = [path for root in roots for path in root.rglob('*')
         if path.is_file() and str(path.relative_to(scripts_root)) not in kept]
raw_bytes = sum(path.stat().st_size for path in files)
if raw_bytes < 90_000_000:
    raise SystemExit('FAIL: excluded script fixtures no longer prove a material payload saving')
print(f'Phone script payload checks passed ({len(files)} files, {raw_bytes} raw bytes excluded).')
PY
