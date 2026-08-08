#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly checker="$script_dir/check-phone-apk-contents.py"
readonly fixture_dir="$(mktemp -d --tmpdir phone-apk-contents-test.XXXXXX)"
trap 'rm -rf -- "$fixture_dir"' EXIT

python3 - "$checker" "$fixture_dir" <<'PY'
import importlib.util
import pathlib
import sys

sys.dont_write_bytecode = True
checker_path = pathlib.Path(sys.argv[1])
fixture = pathlib.Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("phone_apk_contents", checker_path)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

cases = [
    (checker.declared_native_entries,
     '<resources><string-array name="bundled_in_lib"><item>'
     'libsafe_arm64-v8a.so:../escape.so</item></string-array></resources>'),
    (checker.declared_asset_markers,
     '<resources><string-array name="bundled_in_assets"><item>'
     'qml/Safe:../../escape</item></string-array></resources>'),
    (checker.declared_asset_markers,
     '<resources><string-array name="bundled_in_assets">'
     '<item>qml/Same:qml/One</item><item>qml/Same:qml/Two</item>'
     '</string-array></resources>'),
]
for index, (function, contents) in enumerate(cases):
    declaration = fixture / f'invalid-declaration-{index}.xml'
    declaration.write_text(contents, encoding='utf-8')
    checker.DEPENDENCY_XML = declaration
    try:
        function()
    except ValueError:
        continue
    raise AssertionError(f'invalid Qt dependency declaration {index} was accepted')
PY

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
declared_asset_markers = set()
for item in ElementTree.parse(dependency_xml).findall(
        "./string-array[@name='bundled_in_assets']/item"):
    packaged_path = pathlib.PurePosixPath(item.text.split(':', 1)[0])
    marker = packaged_path if packaged_path.name == 'qmldir' else packaged_path / 'qmldir'
    declared_asset_markers.add('assets/' + marker.as_posix())
assert len(declared_libraries) == 21
assert 'lib/arm64-v8a/libqml_QtQuick.2_qtquick2plugin_arm64-v8a.so' in declared_libraries
assert len(declared_asset_markers) == 12
assert 'assets/qml/QtQuick.2/qmldir' in declared_asset_markers
required.update({entry: b'declared-runtime' for entry in declared_libraries})
required.update({entry: b'qmldir' for entry in declared_asset_markers})
for name, omit in [('complete.apk', None), ('partial.apk', 'assets/kept.txt')]:
    with zipfile.ZipFile(root / name, 'w') as archive:
        archive.writestr('assets/cache_assets.txt', '123\nkept.txt\n')
        for entry, data in required.items():
            if entry != omit:
                archive.writestr(entry, data)

invalid_manifests = {
    'cache-traversal.apk': '123\n../escape\n',
    'cache-absolute.apk': '123\n/escape\n',
    'cache-duplicate.apk': '123\nkept.txt\nkept.txt\n',
    'cache-nonascii-stamp.apk': '\u0661\nkept.txt\n',
    'cache-oversized-stamp.apk': '12345678901234567890\nkept.txt\n',
}
for name, manifest in invalid_manifests.items():
    with zipfile.ZipFile(root / name, 'w') as archive:
        archive.writestr('assets/cache_assets.txt', manifest)
        for entry, data in required.items():
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

with (root / 'qml-asset-fixtures.txt').open('w', encoding='utf-8') as fixture_list:
    for index, omitted in enumerate(sorted(declared_asset_markers)):
        fixture = root / f'missing-qml-asset-{index}.apk'
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

for fixture in \
        cache-traversal.apk \
        cache-absolute.apk \
        cache-duplicate.apk \
        cache-nonascii-stamp.apk \
        cache-oversized-stamp.apk; do
    if "$checker" "$fixture_dir/$fixture" >"$fixture_dir/cache-out" 2>&1; then
        printf 'FAIL: unsafe cache manifest was accepted: %s\n' "$fixture" >&2
        exit 1
    fi
done

while IFS=$'\t' read -r fixture omitted; do
    if "$checker" "$fixture" >"$fixture_dir/native-out" 2>&1; then
        printf 'FAIL: APK without required runtime was accepted: %s\n' "$omitted" >&2
        exit 1
    fi
    grep -Fq "missing required entries: $omitted" "$fixture_dir/native-out"
done < "$fixture_dir/native-fixtures.txt"

while IFS=$'\t' read -r fixture omitted; do
    if "$checker" "$fixture" >"$fixture_dir/qml-asset-out" 2>&1; then
        printf 'FAIL: APK without declared QML asset was accepted: %s\n' "$omitted" >&2
        exit 1
    fi
    grep -Fq "missing required entries: $omitted" "$fixture_dir/qml-asset-out"
done < "$fixture_dir/qml-asset-fixtures.txt"

echo 'Phone APK contents checks passed.'
