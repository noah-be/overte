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

python3 - "$fixture_dir" "$script_dir/../apps/phoneInterface/src/main/res/values/qt_dependencies.xml" \
        "$checker" <<'PY'
import importlib.util
import pathlib
import sys
import warnings
import zipfile
from xml.etree import ElementTree

root = pathlib.Path(sys.argv[1])
dependency_xml = pathlib.Path(sys.argv[2])
checker_path = pathlib.Path(sys.argv[3])
spec = importlib.util.spec_from_file_location("phone_apk_contents_fixture", checker_path)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
required = {
    'AndroidManifest.xml': b'manifest',
    'classes.dex': b'dex',
    'assets/resources.rcc': b'resources',
    'assets/android_rcc_bundle.rcc': b'qml',
    'assets/kept.txt': b'kept',
    'lib/arm64-v8a/libphoneInterface.so': b'phone',
    'lib/arm64-v8a/libc++_shared.so': b'cxx',
    'lib/arm64-v8a/libQt5Core_arm64-v8a.so': b'core',
    'lib/arm64-v8a/libQt5Qml_arm64-v8a.so': b'qml-runtime',
    'lib/arm64-v8a/libQt5Quick_arm64-v8a.so': b'quick',
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
required.update({'assets/' + entry: b'required-cache-asset'
                 for entry in checker.REQUIRED_CACHED_ASSETS})
cache_paths = sorted(checker.REQUIRED_CACHED_ASSETS | {'kept.txt'})
cache_manifest = '123\n' + '\n'.join(cache_paths) + '\n'
for name, omit in [('complete.apk', None), ('partial.apk', 'assets/kept.txt')]:
    with zipfile.ZipFile(root / name, 'w') as archive:
        archive.writestr('assets/cache_assets.txt', cache_manifest)
        for entry, data in required.items():
            if entry != omit:
                archive.writestr(entry, data)

with zipfile.ZipFile(root / 'content-digest.apk', 'w') as archive:
    archive.writestr('assets/cache_assets.txt', ('a' * 64) + '\n' +
                     '\n'.join(cache_paths) + '\n')
    for entry, data in required.items():
        archive.writestr(entry, data)

with zipfile.ZipFile(root / 'complete.aab', 'w') as archive:
    archive.writestr('base/assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        if entry == 'AndroidManifest.xml':
            bundle_entry = 'base/manifest/AndroidManifest.xml'
        elif entry == 'classes.dex':
            bundle_entry = 'base/dex/classes.dex'
        else:
            bundle_entry = 'base/' + entry
        archive.writestr(bundle_entry, data)

with zipfile.ZipFile(root / 'missing-runtime.aab', 'w') as archive:
    archive.writestr('base/assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        if entry == 'lib/arm64-v8a/libQt5Core_arm64-v8a.so':
            continue
        if entry == 'AndroidManifest.xml':
            bundle_entry = 'base/manifest/AndroidManifest.xml'
        elif entry == 'classes.dex':
            bundle_entry = 'base/dex/classes.dex'
        else:
            bundle_entry = 'base/' + entry
        archive.writestr(bundle_entry, data)

with zipfile.ZipFile(root / 'unexpected-abi.apk', 'w') as archive:
    archive.writestr('assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        archive.writestr(entry, data)
    archive.writestr('lib/x86_64/libstale.so', b'stale')

with warnings.catch_warnings():
    warnings.simplefilter('ignore', UserWarning)
    with zipfile.ZipFile(root / 'duplicate-entry.apk', 'w') as archive:
        archive.writestr('assets/cache_assets.txt', cache_manifest)
        for entry, data in required.items():
            archive.writestr(entry, data)
        archive.writestr('assets/kept.txt', b'duplicate')

with zipfile.ZipFile(root / 'missing-required-cache-entry.apk', 'w') as archive:
    incomplete_cache_paths = [entry for entry in cache_paths
                              if entry != 'android_rcc_bundle.rcc']
    archive.writestr('assets/cache_assets.txt', '123\n' +
                     '\n'.join(incomplete_cache_paths) + '\n')
    for entry, data in required.items():
        archive.writestr(entry, data)

invalid_manifests = {
    'cache-traversal.apk': '123\n../escape\n',
    'cache-absolute.apk': '123\n/escape\n',
    'cache-duplicate.apk': '123\nkept.txt\nkept.txt\n',
    'cache-nonascii-stamp.apk': '\u0661\nkept.txt\n',
    'cache-oversized-stamp.apk': '12345678901234567890\nkept.txt\n',
    'cache-short-digest.apk': ('a' * 63) + '\nkept.txt\n',
    'cache-nonhex-digest.apk': ('g' * 64) + '\nkept.txt\n',
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
            archive.writestr('assets/cache_assets.txt', cache_manifest)
            for entry, data in required.items():
                if entry != omitted:
                    archive.writestr(entry, data)
        fixture_list.write(f'{fixture}\t{omitted}\n')

with (root / 'qml-asset-fixtures.txt').open('w', encoding='utf-8') as fixture_list:
    for index, omitted in enumerate(sorted(declared_asset_markers)):
        fixture = root / f'missing-qml-asset-{index}.apk'
        with zipfile.ZipFile(fixture, 'w') as archive:
            archive.writestr('assets/cache_assets.txt', cache_manifest)
            for entry, data in required.items():
                if entry != omitted:
                    archive.writestr(entry, data)
        fixture_list.write(f'{fixture}\t{omitted}\n')
PY

"$checker" "$fixture_dir/complete.apk" >/dev/null
"$checker" "$fixture_dir/content-digest.apk" >/dev/null
"$checker" "$fixture_dir/complete.aab" >/dev/null
if "$checker" "$fixture_dir/missing-runtime.aab" >"$fixture_dir/aab-out" 2>&1; then
    echo 'FAIL: AAB missing a required runtime was accepted' >&2
    exit 1
fi
grep -q 'libQt5Core_arm64-v8a.so' "$fixture_dir/aab-out"
if "$checker" "$fixture_dir/missing-required-cache-entry.apk" \
        >"$fixture_dir/required-cache-out" 2>&1; then
    echo 'FAIL: APK with an unextractable required resource bundle was accepted' >&2
    exit 1
fi
grep -Fq 'omits required extracted assets: android_rcc_bundle.rcc' \
    "$fixture_dir/required-cache-out"
for fixture in unexpected-abi.apk duplicate-entry.apk; do
    if "$checker" "$fixture_dir/$fixture" >"$fixture_dir/archive-out" 2>&1; then
        printf 'FAIL: invalid APK archive structure was accepted: %s\n' "$fixture" >&2
        exit 1
    fi
done
grep -Fq 'outside arm64-v8a' "$fixture_dir/archive-out" || \
    grep -Fq 'duplicate ZIP entry names' "$fixture_dir/archive-out"
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
        cache-oversized-stamp.apk \
        cache-short-digest.apk \
        cache-nonhex-digest.apk; do
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
