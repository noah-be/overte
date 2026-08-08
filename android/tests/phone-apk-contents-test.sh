#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly checker="$script_dir/check-phone-apk-contents.py"
readonly fixture_dir="$(mktemp -d --tmpdir phone-apk-contents-test.XXXXXX)"
trap 'rm -rf -- "$fixture_dir"' EXIT

python3 - "$fixture_dir" "$script_dir/../apps/phoneInterface/src/main/res/values/qt_dependencies.xml" <<'PY'
import pathlib
import sys
import zipfile
from xml.etree import ElementTree

root = pathlib.Path(sys.argv[1])
dependency_xml = pathlib.Path(sys.argv[2])
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
}
declared_libraries = {
    'lib/arm64-v8a/' + item.text.split(':', 1)[0]
    for item in ElementTree.parse(dependency_xml).findall(
        "./string-array[@name='bundled_in_lib']/item"
    )
}
assert len(declared_libraries) == 21
assert 'lib/arm64-v8a/libqml_QtQuick.2_qtquick2plugin_arm64-v8a.so' in declared_libraries
required.update({entry: b'declared-runtime' for entry in declared_libraries})
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
