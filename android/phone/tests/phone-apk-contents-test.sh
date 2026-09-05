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
    (checker.declared_asset_markers,
     '<resources><string-array name="bundled_in_assets"><item>'
     'other/Module:other/Module</item></string-array></resources>'),
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
import hashlib
import pathlib
import stat
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
    'lib/arm64-v8a/libcrypto_3.so': b'crypto',
    'lib/arm64-v8a/libssl_3.so': b'ssl',
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
required.update({entry: b'linked-runtime' for entry in checker.LINKED_NATIVE_ENTRIES})
required.update({entry: b'qmldir' for entry in declared_asset_markers})
required.update({'assets/' + entry: b'required-cache-asset'
                 for entry in checker.REQUIRED_CACHED_ASSETS})
cache_paths = sorted(checker.REQUIRED_CACHED_ASSETS | {'kept.txt'})
def cache_manifest_for(paths, contents=required):
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.encode('utf-8'))
        digest.update(b'\0')
        digest.update(contents['assets/' + path])
    return digest.hexdigest() + '\n' + '\n'.join(paths) + '\n'

def corrupt_stored_entry(package, entry):
    with zipfile.ZipFile(package) as archive:
        info = archive.getinfo(entry)
    with package.open('r+b') as output:
        output.seek(info.header_offset)
        local_header = output.read(30)
        assert local_header[:4] == b'PK\x03\x04'
        name_length = int.from_bytes(local_header[26:28], 'little')
        extra_length = int.from_bytes(local_header[28:30], 'little')
        output.seek(info.header_offset + 30 + name_length + extra_length)
        original = output.read(1)
        assert original
        output.seek(-1, 1)
        output.write(bytes([original[0] ^ 1]))

cache_manifest = cache_manifest_for(cache_paths)
for name, omit in [('complete.apk', None), ('partial.apk', 'assets/kept.txt')]:
    with zipfile.ZipFile(root / name, 'w') as archive:
        archive.writestr('assets/cache_assets.txt', cache_manifest)
        for entry, data in required.items():
            if entry != omit:
                archive.writestr(entry, data)

with zipfile.ZipFile(root / 'cache-digest-mismatch.apk', 'w') as archive:
    archive.writestr('assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        archive.writestr(entry, b'tampered' if entry == 'assets/kept.txt' else data)

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

with zipfile.ZipFile(root / 'mixed-layout.aab', 'w') as archive:
    archive.writestr('base/assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        if entry == 'AndroidManifest.xml':
            bundle_entry = 'base/manifest/AndroidManifest.xml'
        elif entry == 'classes.dex':
            bundle_entry = 'base/dex/classes.dex'
        else:
            bundle_entry = 'base/' + entry
        archive.writestr(bundle_entry, data)
    archive.writestr('AndroidManifest.xml', b'stale-apk-manifest')

with zipfile.ZipFile(root / 'unexpected-feature.aab', 'w') as archive:
    archive.writestr('base/assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        if entry == 'AndroidManifest.xml':
            bundle_entry = 'base/manifest/AndroidManifest.xml'
        elif entry == 'classes.dex':
            bundle_entry = 'base/dex/classes.dex'
        else:
            bundle_entry = 'base/' + entry
        archive.writestr(bundle_entry, data)
    archive.writestr('staleFeature/manifest/AndroidManifest.xml', b'stale-feature')

with zipfile.ZipFile(root / 'missing-base-module.aab', 'w') as archive:
    archive.writestr('staleFeature/manifest/AndroidManifest.xml', b'stale-feature')

with zipfile.ZipFile(root / 'cache-digest-mismatch.aab', 'w') as archive:
    archive.writestr('base/assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        if entry == 'AndroidManifest.xml':
            bundle_entry = 'base/manifest/AndroidManifest.xml'
        elif entry == 'classes.dex':
            bundle_entry = 'base/dex/classes.dex'
        else:
            bundle_entry = 'base/' + entry
        archive.writestr(bundle_entry,
                         b'tampered' if entry == 'assets/kept.txt' else data)

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

with zipfile.ZipFile(root / 'unexpected-arm64-runtime.apk', 'w') as archive:
    archive.writestr('assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        archive.writestr(entry, data)
    archive.writestr('lib/arm64-v8a/libstale.so', b'stale')

with zipfile.ZipFile(root / 'unexpected-arm64-runtime.aab', 'w') as archive:
    archive.writestr('base/assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        if entry == 'AndroidManifest.xml':
            bundle_entry = 'base/manifest/AndroidManifest.xml'
        elif entry == 'classes.dex':
            bundle_entry = 'base/dex/classes.dex'
        else:
            bundle_entry = 'base/' + entry
        archive.writestr(bundle_entry, data)
    archive.writestr('base/lib/arm64-v8a/libstale.so', b'stale')

corrupt_apk = root / 'corrupt-required-entry.apk'
with zipfile.ZipFile(corrupt_apk, 'w') as archive:
    archive.writestr('assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        archive.writestr(entry, data)
corrupt_stored_entry(corrupt_apk, 'classes.dex')

corrupt_aab = root / 'corrupt-required-entry.aab'
with zipfile.ZipFile(corrupt_aab, 'w') as archive:
    archive.writestr('base/assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        if entry == 'AndroidManifest.xml':
            bundle_entry = 'base/manifest/AndroidManifest.xml'
        elif entry == 'classes.dex':
            bundle_entry = 'base/dex/classes.dex'
        else:
            bundle_entry = 'base/' + entry
        archive.writestr(bundle_entry, data)
corrupt_stored_entry(corrupt_aab, 'base/lib/arm64-v8a/libphoneInterface.so')

corrupt_extra_apk = root / 'corrupt-extra-entry.apk'
with zipfile.ZipFile(corrupt_extra_apk, 'w') as archive:
    archive.writestr('assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        archive.writestr(entry, data)
    archive.writestr('assets/qml/QtQml/optional-qt-metadata.dat', b'optional')
corrupt_stored_entry(corrupt_extra_apk, 'assets/qml/QtQml/optional-qt-metadata.dat')

corrupt_extra_aab = root / 'corrupt-extra-entry.aab'
with zipfile.ZipFile(corrupt_extra_aab, 'w') as archive:
    archive.writestr('base/assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        if entry == 'AndroidManifest.xml':
            bundle_entry = 'base/manifest/AndroidManifest.xml'
        elif entry == 'classes.dex':
            bundle_entry = 'base/dex/classes.dex'
        else:
            bundle_entry = 'base/' + entry
        archive.writestr(bundle_entry, data)
    archive.writestr('BUNDLE-METADATA/com.android.tools.build/metadata.pb', b'metadata')
corrupt_stored_entry(
    corrupt_extra_aab,
    'BUNDLE-METADATA/com.android.tools.build/metadata.pb',
)

with warnings.catch_warnings():
    warnings.simplefilter('ignore', UserWarning)
    with zipfile.ZipFile(root / 'duplicate-entry.apk', 'w') as archive:
        archive.writestr('assets/cache_assets.txt', cache_manifest)
        for entry, data in required.items():
            archive.writestr(entry, data)
        archive.writestr('assets/kept.txt', b'duplicate')

with zipfile.ZipFile(root / 'directory-with-data.apk', 'w') as archive:
    archive.writestr('assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        archive.writestr(entry, data)
    archive.writestr('assets/optional-directory/', b'unexpected data')

with zipfile.ZipFile(root / 'symlink-entry.apk', 'w') as archive:
    archive.writestr('assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        archive.writestr(entry, data)
    link = zipfile.ZipInfo('assets/optional-link')
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    archive.writestr(link, b'kept.txt')

with zipfile.ZipFile(root / 'symlink-entry.aab', 'w') as archive:
    archive.writestr('base/assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        if entry == 'AndroidManifest.xml':
            bundle_entry = 'base/manifest/AndroidManifest.xml'
        elif entry == 'classes.dex':
            bundle_entry = 'base/dex/classes.dex'
        else:
            bundle_entry = 'base/' + entry
        archive.writestr(bundle_entry, data)
    link = zipfile.ZipInfo('BUNDLE-METADATA/optional-link')
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    archive.writestr(link, b'metadata.pb')

for fixture_name, unsafe_entry in (
    ('traversing-extra-entry.apk', '../outside'),
    ('absolute-extra-entry.apk', '/absolute'),
    ('dot-segment-extra-entry.apk', 'assets/./alias'),
    ('repeated-separator-extra-entry.apk', 'assets//alias'),
    ('backslash-extra-entry.apk', r'assets\alias'),
    ('control-extra-entry.apk', 'assets/unsafe\nname'),
):
    with zipfile.ZipFile(root / fixture_name, 'w') as archive:
        archive.writestr('assets/cache_assets.txt', cache_manifest)
        for entry, data in required.items():
            archive.writestr(entry, data)
        archive.writestr(unsafe_entry, b'unsafe')

with zipfile.ZipFile(root / 'traversing-extra-entry.aab', 'w') as archive:
    archive.writestr('base/assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        if entry == 'AndroidManifest.xml':
            bundle_entry = 'base/manifest/AndroidManifest.xml'
        elif entry == 'classes.dex':
            bundle_entry = 'base/dex/classes.dex'
        else:
            bundle_entry = 'base/' + entry
        archive.writestr(bundle_entry, data)
    archive.writestr('base/../../outside', b'unsafe')

with (root / 'oversized-package.apk').open('wb') as package:
    package.truncate(checker.MAX_PACKAGE_BYTES + 1)

with zipfile.ZipFile(root / 'too-many-entries.apk', 'w') as archive:
    for index in range(checker.MAX_PACKAGE_ENTRIES + 1):
        archive.writestr(f'extra/{index}', b'')

for fixture_name, undeclared_asset in (
    ('undeclared-script.apk', 'assets/scripts/stale.js'),
    ('undeclared-rcc.apk', 'assets/stale.rcc'),
):
    with zipfile.ZipFile(root / fixture_name, 'w') as archive:
        archive.writestr('assets/cache_assets.txt', cache_manifest)
        for entry, data in required.items():
            archive.writestr(entry, data)
        archive.writestr(undeclared_asset, b'stale')

with zipfile.ZipFile(root / 'undeclared-script.aab', 'w') as archive:
    archive.writestr('base/assets/cache_assets.txt', cache_manifest)
    for entry, data in required.items():
        if entry == 'AndroidManifest.xml':
            bundle_entry = 'base/manifest/AndroidManifest.xml'
        elif entry == 'classes.dex':
            bundle_entry = 'base/dex/classes.dex'
        else:
            bundle_entry = 'base/' + entry
        archive.writestr(bundle_entry, data)
    archive.writestr('base/assets/scripts/stale.js', b'stale')

for fixture_name, prefix in (
    ('undeclared-qml-module.apk', ''),
    ('undeclared-qml-module.aab', 'base/'),
):
    with zipfile.ZipFile(root / fixture_name, 'w') as archive:
        archive.writestr(prefix + 'assets/cache_assets.txt', cache_manifest)
        for entry, data in required.items():
            if prefix and entry == 'AndroidManifest.xml':
                package_entry = 'base/manifest/AndroidManifest.xml'
            elif prefix and entry == 'classes.dex':
                package_entry = 'base/dex/classes.dex'
            else:
                package_entry = prefix + entry
            archive.writestr(package_entry, data)
        archive.writestr(prefix + 'assets/qml/Unreviewed/qmldir', b'module Unreviewed')

with zipfile.ZipFile(root / 'missing-required-cache-entry.apk', 'w') as archive:
    incomplete_cache_paths = [entry for entry in cache_paths
                              if entry != 'android_rcc_bundle.rcc']
    archive.writestr('assets/cache_assets.txt',
                     cache_manifest_for(incomplete_cache_paths))
    for entry, data in required.items():
        archive.writestr(entry, data)

invalid_manifests = {
    'cache-legacy-timestamp.apk': '123\nkept.txt\n',
    'cache-traversal.apk': ('a' * 64) + '\n../escape\n',
    'cache-absolute.apk': ('a' * 64) + '\n/escape\n',
    'cache-duplicate.apk': ('a' * 64) + '\nkept.txt\nkept.txt\n',
    'cache-unsorted.apk': ('a' * 64) + '\nkept.txt\nandroid_rcc_bundle.rcc\n',
    'cache-nonascii-stamp.apk': '\u0661\nkept.txt\n',
    'cache-oversized-stamp.apk': '12345678901234567890\nkept.txt\n',
    'cache-short-digest.apk': ('a' * 63) + '\nkept.txt\n',
    'cache-nonhex-digest.apk': ('g' * 64) + '\nkept.txt\n',
    'cache-oversized-manifest.apk': 'a' * (checker.MAX_CACHE_MANIFEST_BYTES + 1),
    'cache-too-many-assets.apk': ('a' * 64) + '\n' +
        '\n'.join(f'asset-{index}' for index in range(checker.MAX_CACHE_ASSET_COUNT + 1)) + '\n',
    'cache-overlong-path.apk': ('a' * 64) + '\n' +
        ('a' * (checker.MAX_CACHE_PATH_BYTES + 1)) + '\n',
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
"$checker" "$fixture_dir/complete.aab" >/dev/null
if "$checker" "$fixture_dir/cache-digest-mismatch.apk" \
        >"$fixture_dir/digest-out" 2>&1; then
    echo 'FAIL: APK with mismatched cache content digest was accepted' >&2
    exit 1
fi
grep -Fq 'content digest does not match packaged assets' "$fixture_dir/digest-out"
if "$checker" "$fixture_dir/cache-digest-mismatch.aab" \
        >"$fixture_dir/aab-digest-out" 2>&1; then
    echo 'FAIL: AAB with mismatched cache content digest was accepted' >&2
    exit 1
fi
grep -Fq 'content digest does not match packaged assets' \
    "$fixture_dir/aab-digest-out"
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
while IFS=$'\t' read -r fixture expected_error; do
    if "$checker" "$fixture_dir/$fixture" >"$fixture_dir/archive-out" 2>&1; then
        printf 'FAIL: invalid APK archive structure was accepted: %s\n' "$fixture" >&2
        exit 1
    fi
    grep -Fq "$expected_error" "$fixture_dir/archive-out"
done <<'ARCHIVE_CASES'
unexpected-abi.apk	outside arm64-v8a
unexpected-arm64-runtime.apk	unexpected ARM64 native entries
unexpected-arm64-runtime.aab	unexpected ARM64 native entries
duplicate-entry.apk	duplicate ZIP entry names
directory-with-data.apk	directory entry contains file data
symlink-entry.apk	contains symbolic link entries
symlink-entry.aab	contains symbolic link entries
traversing-extra-entry.apk	contains an unsafe ZIP entry path
absolute-extra-entry.apk	contains an unsafe ZIP entry path
dot-segment-extra-entry.apk	contains an unsafe ZIP entry path
repeated-separator-extra-entry.apk	contains an unsafe ZIP entry path
backslash-extra-entry.apk	contains an unsafe ZIP entry path
control-extra-entry.apk	contains an unsafe ZIP entry path
traversing-extra-entry.aab	contains an unsafe ZIP entry path
mixed-layout.aab	mixes APK and Android App Bundle entry layouts
unexpected-feature.aab	contains unexpected feature modules
missing-base-module.aab	has no base manifest module
ARCHIVE_CASES

for fixture in \
        corrupt-required-entry.apk \
        corrupt-required-entry.aab \
        corrupt-extra-entry.apk \
        corrupt-extra-entry.aab; do
    if "$checker" "$fixture_dir/$fixture" >"$fixture_dir/integrity-out" 2>&1; then
        printf 'FAIL: package with a corrupt required entry was accepted: %s\n' \
            "$fixture" >&2
        exit 1
    fi
    grep -Fxq 'ERROR: Android phone package ZIP data is invalid' \
        "$fixture_dir/integrity-out"
done

if "$checker" "$fixture_dir/private/missing.apk" \
        >"$fixture_dir/missing-input-out" 2>&1; then
    echo 'FAIL: missing package input was accepted' >&2
    exit 1
fi
grep -Fxq 'ERROR: could not read Android phone package input' \
    "$fixture_dir/missing-input-out"
! grep -Fq "$fixture_dir" "$fixture_dir/missing-input-out"
if "$checker" "$fixture_dir/partial.apk" >"$fixture_dir/out" 2>&1; then
    echo 'FAIL: incomplete APK fixture was accepted' >&2
    exit 1
fi
grep -q '1 cache assets are absent' "$fixture_dir/out"

for fixture in \
        cache-legacy-timestamp.apk \
        cache-traversal.apk \
        cache-absolute.apk \
        cache-duplicate.apk \
        cache-unsorted.apk \
        cache-nonascii-stamp.apk \
        cache-oversized-stamp.apk \
        cache-short-digest.apk \
        cache-nonhex-digest.apk; do
    if "$checker" "$fixture_dir/$fixture" >"$fixture_dir/cache-out" 2>&1; then
        printf 'FAIL: unsafe cache manifest was accepted: %s\n' "$fixture" >&2
        exit 1
    fi
done

while IFS=$'\t' read -r fixture expected_error; do
    if "$checker" "$fixture_dir/$fixture" >"$fixture_dir/limit-out" 2>&1; then
        printf 'FAIL: over-limit cache manifest was accepted: %s\n' "$fixture" >&2
        exit 1
    fi
    grep -Fq "$expected_error" "$fixture_dir/limit-out"
done <<'LIMIT_CASES'
cache-oversized-manifest.apk	exceeds the size limit
cache-too-many-assets.apk	exceeds the asset-count limit
cache-overlong-path.apk	contains an overlong asset path
LIMIT_CASES

while IFS=$'\t' read -r fixture expected_error; do
    if "$checker" "$fixture_dir/$fixture" >"$fixture_dir/package-limit-out" 2>&1; then
        printf 'FAIL: over-limit package was accepted: %s\n' "$fixture" >&2
        exit 1
    fi
    grep -Fq "$expected_error" "$fixture_dir/package-limit-out"
done <<'PACKAGE_LIMIT_CASES'
oversized-package.apk	package exceeds the size limit
too-many-entries.apk	package exceeds the ZIP entry-count limit
PACKAGE_LIMIT_CASES

for fixture in undeclared-script.apk undeclared-rcc.apk undeclared-script.aab; do
    if "$checker" "$fixture_dir/$fixture" >"$fixture_dir/asset-coverage-out" 2>&1; then
        printf 'FAIL: package with an undeclared managed asset was accepted: %s\n' \
            "$fixture" >&2
        exit 1
    fi
    grep -Fq 'assets outside cache_assets.txt' "$fixture_dir/asset-coverage-out"
done

for fixture in undeclared-qml-module.apk undeclared-qml-module.aab; do
    if "$checker" "$fixture_dir/$fixture" >"$fixture_dir/qml-boundary-out" 2>&1; then
        printf 'FAIL: package with an undeclared QML module was accepted: %s\n' \
            "$fixture" >&2
        exit 1
    fi
    grep -Fq 'QML outside declared module roots' "$fixture_dir/qml-boundary-out"
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
