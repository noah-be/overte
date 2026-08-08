#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly checker="$script_dir/check-phone-apk-contents.py"
readonly fixture_dir="$(mktemp -d --tmpdir phone-apk-contents-test.XXXXXX)"
trap 'rm -rf -- "$fixture_dir"' EXIT

python3 - "$fixture_dir" <<'PY'
import pathlib
import sys
import zipfile

root = pathlib.Path(sys.argv[1])
required = {
    'AndroidManifest.xml': b'manifest',
    'classes.dex': b'dex',
    'assets/resources.rcc': b'resources',
    'assets/android_rcc_bundle.rcc': b'qml',
    'assets/kept.txt': b'kept',
    'lib/arm64-v8a/libphoneInterface.so': b'phone',
    'lib/arm64-v8a/libplugins_platforms_qtforandroid_arm64-v8a.so': b'platform',
}
for name, omit in [('complete.apk', None), ('partial.apk', 'assets/kept.txt')]:
    with zipfile.ZipFile(root / name, 'w') as archive:
        archive.writestr('assets/cache_assets.txt', '123\nkept.txt\n')
        for entry, data in required.items():
            if entry != omit:
                archive.writestr(entry, data)
PY

"$checker" "$fixture_dir/complete.apk" >/dev/null
if "$checker" "$fixture_dir/partial.apk" >"$fixture_dir/out" 2>&1; then
    echo 'FAIL: incomplete APK fixture was accepted' >&2
    exit 1
fi
grep -q '1 cache assets are absent' "$fixture_dir/out"
echo 'Phone APK contents checks passed.'
