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
    'lib/arm64-v8a/libQt5PositioningQuick_arm64-v8a.so': b'positioning',
    'lib/arm64-v8a/libcrypto_1_1.so': b'crypto',
    'lib/arm64-v8a/libssl_1_1.so': b'ssl',
    'lib/arm64-v8a/libplugins_audio_qtaudio_opensles_arm64-v8a.so': b'audio',
    'lib/arm64-v8a/libplugins_bearer_qandroidbearer_arm64-v8a.so': b'bearer',
    'lib/arm64-v8a/libplugins_imageformats_qjpeg_arm64-v8a.so': b'jpeg',
    'lib/arm64-v8a/libplugins_imageformats_qsvg_arm64-v8a.so': b'svg',
    'lib/arm64-v8a/libplugins_platforms_qtforandroid_arm64-v8a.so': b'platform',
}
for name, omit in [('complete.apk', None), ('partial.apk', 'assets/kept.txt')]:
    with zipfile.ZipFile(root / name, 'w') as archive:
        archive.writestr('assets/cache_assets.txt', '123\nkept.txt\n')
        for entry, data in required.items():
            if entry != omit:
                archive.writestr(entry, data)

native_entries = sorted(entry for entry in required if entry.startswith('lib/'))
with (root / 'native-fixtures.txt').open('w', encoding='utf-8') as fixture_list:
    for index, omitted in enumerate(native_entries):
        fixture = root / f'missing-native-{index}.apk'
        with zipfile.ZipFile(fixture, 'w') as archive:
            archive.writestr('assets/cache_assets.txt', '123\nkept.txt\n')
            for entry, data in required.items():
                if entry != omitted:
                    archive.writestr(entry, data)
        fixture_list.write(f'{fixture}\t{omitted}\n')
PY

"$checker" "$fixture_dir/complete.apk" >/dev/null
if "$checker" "$fixture_dir/partial.apk" >"$fixture_dir/out" 2>&1; then
    echo 'FAIL: incomplete APK fixture was accepted' >&2
    exit 1
fi
grep -q '1 cache assets are absent' "$fixture_dir/out"

while IFS=$'\t' read -r fixture omitted; do
    if "$checker" "$fixture" >"$fixture_dir/native-out" 2>&1; then
        printf 'FAIL: APK without required runtime was accepted: %s\n' "$omitted" >&2
        exit 1
    fi
    grep -Fq "missing required entries: $omitted" "$fixture_dir/native-out"
done < "$fixture_dir/native-fixtures.txt"

echo 'Phone APK contents checks passed.'
