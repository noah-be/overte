#!/usr/bin/env python3

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
    "lib/arm64-v8a/libQt5PositioningQuick_arm64-v8a.so",
    "lib/arm64-v8a/libcrypto_1_1.so",
    "lib/arm64-v8a/libssl_1_1.so",
}
DEPENDENCY_XML = (
    Path(__file__).resolve().parents[1]
    / "apps/phoneInterface/src/main/res/values/qt_dependencies.xml"
)


def is_safe_relative_path(value):
    path = PurePosixPath(value)
    return value not in ("", ".") and not path.is_absolute() and ".." not in path.parts


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
            names = set(archive.namelist())
            missing = required_entries - names
            if missing:
                raise ValueError("missing required entries: " + ", ".join(sorted(missing)))

            cache_lines = archive.read("assets/cache_assets.txt").decode("utf-8").splitlines()
            if (
                len(cache_lines) < 2
                or not cache_lines[0].isascii()
                or not cache_lines[0].isdigit()
                or len(cache_lines[0]) > 19
            ):
                raise ValueError("invalid cache_assets.txt header")
            cache_paths = cache_lines[1:]
            if any(not is_safe_relative_path(path) for path in cache_paths):
                raise ValueError("cache_assets.txt contains an unsafe asset path")
            if len(cache_paths) != len(set(cache_paths)):
                raise ValueError("cache_assets.txt contains a duplicate asset path")
            declared_assets = {"assets/" + path for path in cache_paths}
            missing_assets = declared_assets - names
            if missing_assets:
                preview = ", ".join(sorted(missing_assets)[:5])
                raise ValueError(
                    f"{len(missing_assets)} cache assets are absent" +
                    (f" (first: {preview})" if preview else "")
                )
    except (
        ElementTree.ParseError,
        OSError,
        UnicodeError,
        ValueError,
        zipfile.BadZipFile,
    ) as error:
        print(f"ERROR: incomplete Android phone APK: {error}", file=sys.stderr)
        return 1

    print(f"APK contents are complete ({len(declared_assets)} declared assets present).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
