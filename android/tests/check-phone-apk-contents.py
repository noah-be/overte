#!/usr/bin/env python3

import hashlib
import sys
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree


BASE_REQUIRED_ENTRIES = {
    "AndroidManifest.xml",
    "classes.dex",
    "assets/cache_assets.txt",
    "assets/resources.rcc",
    "assets/android_rcc_bundle.rcc",
    "lib/arm64-v8a/libphoneInterface.so",
    "lib/arm64-v8a/libc++_shared.so",
    "lib/arm64-v8a/libQt5Core_arm64-v8a.so",
    "lib/arm64-v8a/libQt5Qml_arm64-v8a.so",
    "lib/arm64-v8a/libQt5Quick_arm64-v8a.so",
    "lib/arm64-v8a/libQt5PositioningQuick_arm64-v8a.so",
    "lib/arm64-v8a/libcrypto_1_1.so",
    "lib/arm64-v8a/libssl_1_1.so",
}
DEPENDENCY_XML = (
    Path(__file__).resolve().parents[1]
    / "apps/phoneInterface/src/main/res/values/qt_dependencies.xml"
)
REQUIRED_CACHED_ASSETS = {
    "resources.rcc",
    "android_rcc_bundle.rcc",
    "scripts/+android_phoneInterface/defaultScripts.js",
    "scripts/system/request-service.js",
    "scripts/system/progress.js",
    "scripts/system/+android_interface/touchscreenvirtualpad.js",
    "scripts/system/+android_interface/androidControls.js",
    "scripts/system/+android_phoneInterface/mobileActionBar.js",
    "scripts/system/+android_phoneInterface/mobileTabletApps.js",
    "scripts/system/+android_phoneInterface/phoneEmote.js",
    "scripts/system/bubble.js",
    "scripts/system/pal.js",
    "scripts/system/avatarapp.js",
    "scripts/system/places/places.js",
    "scripts/system/quickGoto.js",
}


def is_safe_relative_path(value):
    path = PurePosixPath(value)
    return value not in ("", ".") and not path.is_absolute() and ".." not in path.parts


def logical_package_names(archive_names):
    is_bundle = "base/manifest/AndroidManifest.xml" in archive_names
    if not is_bundle:
        return archive_names, "assets/cache_assets.txt"

    logical = []
    for name in archive_names:
        if name == "base/manifest/AndroidManifest.xml":
            logical.append("AndroidManifest.xml")
        elif name.startswith("base/dex/"):
            logical.append(name[len("base/dex/"):])
        elif name.startswith("base/assets/") or name.startswith("base/lib/"):
            logical.append(name[len("base/"):])
    return logical, "base/assets/cache_assets.txt"


def cached_asset_entry(cache_manifest_entry, path):
    prefix = cache_manifest_entry.removesuffix("cache_assets.txt")
    return prefix + path


def cache_content_digest(archive, cache_manifest_entry, cache_paths):
    digest = hashlib.sha256()
    for path in cache_paths:
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        with archive.open(cached_asset_entry(cache_manifest_entry, path)) as asset:
            while chunk := asset.read(64 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def declared_native_entries():
    root = ElementTree.parse(DEPENDENCY_XML).getroot()
    bundled = root.find("./string-array[@name='bundled_in_lib']")
    if bundled is None:
        raise ValueError("qt_dependencies.xml has no bundled_in_lib array")

    entries = set()
    for item in bundled.findall("item"):
        declaration = (item.text or "").strip()
        packaged_name, separator, runtime_path = declaration.partition(":")
        if (
            not separator
            or not is_safe_relative_path(runtime_path)
            or packaged_name != Path(packaged_name).name
            or not packaged_name.endswith("_arm64-v8a.so")
        ):
            raise ValueError(
                "invalid bundled native dependency declaration: " + declaration
            )
        archive_entry = "lib/arm64-v8a/" + packaged_name
        if archive_entry in entries:
            raise ValueError(
                "duplicate bundled native dependency declaration: " + packaged_name
            )
        entries.add(archive_entry)
    if not entries:
        raise ValueError("qt_dependencies.xml declares no bundled native libraries")
    return entries


def declared_asset_markers():
    root = ElementTree.parse(DEPENDENCY_XML).getroot()
    bundled = root.find("./string-array[@name='bundled_in_assets']")
    if bundled is None:
        raise ValueError("qt_dependencies.xml has no bundled_in_assets array")

    entries = set()
    for item in bundled.findall("item"):
        declaration = (item.text or "").strip()
        packaged_path, separator, runtime_path = declaration.partition(":")
        path = PurePosixPath(packaged_path)
        if (
            not separator
            or not is_safe_relative_path(packaged_path)
            or not is_safe_relative_path(runtime_path)
        ):
            raise ValueError(
                "invalid bundled asset dependency declaration: " + declaration
            )
        marker = path if path.name == "qmldir" else path / "qmldir"
        archive_entry = "assets/" + marker.as_posix()
        if archive_entry in entries:
            raise ValueError(
                "duplicate bundled asset dependency declaration: " + packaged_path
            )
        entries.add(archive_entry)
    if not entries:
        raise ValueError("qt_dependencies.xml declares no bundled QML assets")
    return entries


def main():
    if len(sys.argv) != 2:
        print("Usage: check-phone-apk-contents.py <apk>", file=sys.stderr)
        return 2
    try:
        required_entries = (
            BASE_REQUIRED_ENTRIES
            | declared_native_entries()
            | declared_asset_markers()
        )
        with zipfile.ZipFile(sys.argv[1]) as archive:
            raw_archive_names = archive.namelist()
            if len(raw_archive_names) != len(set(raw_archive_names)):
                raise ValueError("package contains duplicate ZIP entry names")
            archive_names, cache_manifest_entry = logical_package_names(raw_archive_names)
            names = set(archive_names)
            if len(archive_names) != len(names):
                raise ValueError("package contains duplicate logical entry names")
            unexpected_native_abis = sorted(
                name for name in names
                if name.startswith("lib/") and not name.startswith("lib/arm64-v8a/")
            )
            if unexpected_native_abis:
                raise ValueError(
                    "APK contains native entries outside arm64-v8a: "
                    + ", ".join(unexpected_native_abis[:5])
                )
            missing = required_entries - names
            if missing:
                raise ValueError("missing required entries: " + ", ".join(sorted(missing)))

            cache_lines = archive.read(cache_manifest_entry).decode("utf-8").splitlines()
            if (
                len(cache_lines) < 2
                or len(cache_lines[0]) != 64
                or any(character not in "0123456789abcdef" for character in cache_lines[0])
            ):
                raise ValueError("invalid cache_assets.txt header")
            cache_paths = cache_lines[1:]
            if any(not is_safe_relative_path(path) for path in cache_paths):
                raise ValueError("cache_assets.txt contains an unsafe asset path")
            if len(cache_paths) != len(set(cache_paths)):
                raise ValueError("cache_assets.txt contains a duplicate asset path")
            if cache_paths != sorted(cache_paths):
                raise ValueError("cache_assets.txt asset paths are not sorted")
            missing_cached_assets = REQUIRED_CACHED_ASSETS - set(cache_paths)
            if missing_cached_assets:
                raise ValueError(
                    "cache_assets.txt omits required extracted assets: "
                    + ", ".join(sorted(missing_cached_assets))
                )
            declared_assets = {"assets/" + path for path in cache_paths}
            missing_assets = declared_assets - names
            if missing_assets:
                preview = ", ".join(sorted(missing_assets)[:5])
                raise ValueError(
                    f"{len(missing_assets)} cache assets are absent" +
                    (f" (first: {preview})" if preview else "")
                )
            if cache_content_digest(archive, cache_manifest_entry, cache_paths) != cache_lines[0]:
                raise ValueError("cache_assets.txt content digest does not match packaged assets")
    except (
        ElementTree.ParseError,
        OSError,
        UnicodeError,
        ValueError,
        zipfile.BadZipFile,
    ) as error:
        print(f"ERROR: incomplete Android phone package: {error}", file=sys.stderr)
        return 1

    print(f"Android package contents are complete ({len(declared_assets)} declared assets present).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
