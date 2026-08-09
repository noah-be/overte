#!/usr/bin/env python3

import hashlib
import stat
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
# Native libraries linked into the modular phoneInterface build. Qt's
# bundled_in_lib declaration only describes libraries copied into Qt's runtime
# tree; it deliberately does not enumerate ELF dependencies loaded by Android's
# native linker. Keep this exact allowlist fail-closed so a newly introduced
# native payload must be reviewed before it can enter an APK or App Bundle.
LINKED_NATIVE_LIBRARY_NAMES = {
    "libQt5Concurrent_arm64-v8a.so",
    "libQt5Gui_arm64-v8a.so",
    "libQt5Help_arm64-v8a.so",
    "libQt5Location_arm64-v8a.so",
    "libQt5MultimediaQuick_arm64-v8a.so",
    "libQt5MultimediaWidgets_arm64-v8a.so",
    "libQt5Multimedia_arm64-v8a.so",
    "libQt5Network_arm64-v8a.so",
    "libQt5OpenGL_arm64-v8a.so",
    "libQt5Positioning_arm64-v8a.so",
    "libQt5PrintSupport_arm64-v8a.so",
    "libQt5QmlModels_arm64-v8a.so",
    "libQt5QmlWorkerScript_arm64-v8a.so",
    "libQt5QuickControls2_arm64-v8a.so",
    "libQt5QuickShapes_arm64-v8a.so",
    "libQt5QuickTemplates2_arm64-v8a.so",
    "libQt5QuickTest_arm64-v8a.so",
    "libQt5QuickWidgets_arm64-v8a.so",
    "libQt5Scxml_arm64-v8a.so",
    "libQt5Sql_arm64-v8a.so",
    "libQt5Svg_arm64-v8a.so",
    "libQt5Test_arm64-v8a.so",
    "libQt5WebChannel_arm64-v8a.so",
    "libQt5WebSockets_arm64-v8a.so",
    "libQt5WebView_arm64-v8a.so",
    "libQt5Widgets_arm64-v8a.so",
    "libQt5XmlPatterns_arm64-v8a.so",
    "libQt5Xml_arm64-v8a.so",
    "libanimation.so",
    "libaudio-client.so",
    "libaudio.so",
    "libauto-updater.so",
    "libavatars-renderer.so",
    "libavatars.so",
    "libcontrollers.so",
    "libcrypto.so",
    "libdisplay-plugins.so",
    "libentities-renderer.so",
    "libentities.so",
    "libgl.so",
    "libgpu-gl-common.so",
    "libgpu-gl.so",
    "libgpu.so",
    "libgraphics-scripting.so",
    "libgraphics.so",
    "libhfm.so",
    "libimage.so",
    "libinput-plugins.so",
    "libinterface.so",
    "libktx.so",
    "libmaterial-networking.so",
    "libmidi.so",
    "libmodel-baker.so",
    "libmodel-networking.so",
    "libmodel-serializers.so",
    "libnetworking.so",
    "libnode.so",
    "liboctree.so",
    "libphysics.so",
    "libplatform.so",
    "libplugins.so",
    "libpointers.so",
    "libprocedural.so",
    "libqml.so",
    "librecording.so",
    "librender-utils.so",
    "librender.so",
    "libscript-engine.so",
    "libshaders.so",
    "libshared.so",
    "libssl.so",
    "libtask.so",
    "libtbb_debug.so",
    "libui-plugins.so",
    "libui.so",
    "libwebrtc-audio-processing-2.so",
    "libworkload.so",
}
LINKED_NATIVE_ENTRIES = {
    "lib/arm64-v8a/" + name for name in LINKED_NATIVE_LIBRARY_NAMES
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
MAX_CACHE_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_CACHE_ASSET_COUNT = 32 * 1024
MAX_CACHE_PATH_BYTES = 1024
MAX_PACKAGE_BYTES = 4 * 1024 * 1024 * 1024 - 1
MAX_PACKAGE_ENTRIES = 32 * 1024


def is_safe_relative_path(value):
    path = PurePosixPath(value)
    canonical = path.as_posix() + ("/" if value.endswith("/") else "")
    return (
        value not in ("", ".")
        and value == canonical
        and not path.is_absolute()
        and ".." not in path.parts
        and "\\" not in value
        and all(character.isprintable() and not character.isspace() for character in value)
    )


def validate_package_layout(archive_names):
    module_manifests = {
        PurePosixPath(name).parts[0]
        for name in archive_names
        if len(PurePosixPath(name).parts) == 3
        and PurePosixPath(name).parts[1:] == ("manifest", "AndroidManifest.xml")
    }
    if "base" not in module_manifests:
        if module_manifests:
            raise ValueError("Android App Bundle has no base manifest module")
        return
    unexpected_modules = module_manifests - {"base"}
    if unexpected_modules:
        raise ValueError(
            "Android App Bundle contains unexpected feature modules: "
            + ", ".join(sorted(unexpected_modules)[:5])
        )
    mixed_root_entries = {
        name for name in archive_names
        if name == "AndroidManifest.xml"
        or ("/" not in name and name.startswith("classes") and name.endswith(".dex"))
        or name.startswith("assets/")
        or name.startswith("lib/")
    }
    if mixed_root_entries:
        raise ValueError("package mixes APK and Android App Bundle entry layouts")


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


def verify_entry_integrity(archive, entry):
    with archive.open(entry) as packaged_file:
        while packaged_file.read(64 * 1024):
            pass


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


def declared_asset_roots():
    root = ElementTree.parse(DEPENDENCY_XML).getroot()
    bundled = root.find("./string-array[@name='bundled_in_assets']")
    if bundled is None:
        raise ValueError("qt_dependencies.xml has no bundled_in_assets array")

    roots = set()
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
        root_path = path.parent if path.name == "qmldir" else path
        if len(root_path.parts) < 2 or root_path.parts[0] != "qml":
            raise ValueError(
                "bundled asset dependency is outside the QML module root: "
                + declaration
            )
        if root_path in roots:
            raise ValueError(
                "duplicate bundled asset dependency declaration: " + packaged_path
            )
        roots.add(root_path)
    if not roots:
        raise ValueError("qt_dependencies.xml declares no bundled QML assets")
    return roots


def declared_asset_markers():
    return {
        "assets/" + (root / "qmldir").as_posix()
        for root in declared_asset_roots()
    }


def main():
    if len(sys.argv) != 2:
        print("Usage: check-phone-apk-contents.py <apk>", file=sys.stderr)
        return 2
    try:
        required_entries = (
            BASE_REQUIRED_ENTRIES
            | LINKED_NATIVE_ENTRIES
            | declared_native_entries()
            | declared_asset_markers()
        )
        qml_asset_roots = declared_asset_roots()
        if Path(sys.argv[1]).stat().st_size > MAX_PACKAGE_BYTES:
            raise ValueError("package exceeds the size limit")
        with zipfile.ZipFile(sys.argv[1]) as archive:
            if len(archive.infolist()) > MAX_PACKAGE_ENTRIES:
                raise ValueError("package exceeds the ZIP entry-count limit")
            raw_archive_names = archive.namelist()
            if len(raw_archive_names) != len(set(raw_archive_names)):
                raise ValueError("package contains duplicate ZIP entry names")
            if any(not is_safe_relative_path(name) for name in raw_archive_names):
                raise ValueError("package contains an unsafe ZIP entry path")
            if any(
                stat.S_ISLNK(entry.external_attr >> 16)
                for entry in archive.infolist()
            ):
                raise ValueError("package contains symbolic link entries")
            validate_package_layout(raw_archive_names)
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
            packaged_native_entries = {
                name for name in names if name.startswith("lib/arm64-v8a/")
            }
            expected_native_entries = {
                name for name in required_entries if name.startswith("lib/arm64-v8a/")
            }
            unexpected_native_entries = packaged_native_entries - expected_native_entries
            if unexpected_native_entries:
                raise ValueError(
                    "package contains unexpected ARM64 native entries: "
                    + ", ".join(sorted(unexpected_native_entries)[:5])
                )
            missing = required_entries - names
            if missing:
                raise ValueError("missing required entries: " + ", ".join(sorted(missing)))

            cache_manifest_info = archive.getinfo(cache_manifest_entry)
            if cache_manifest_info.file_size > MAX_CACHE_MANIFEST_BYTES:
                raise ValueError("cache_assets.txt exceeds the size limit")
            cache_lines = archive.read(cache_manifest_info).decode("utf-8").splitlines()
            if (
                len(cache_lines) < 2
                or len(cache_lines[0]) != 64
                or any(character not in "0123456789abcdef" for character in cache_lines[0])
            ):
                raise ValueError("invalid cache_assets.txt header")
            cache_paths = cache_lines[1:]
            if len(cache_paths) > MAX_CACHE_ASSET_COUNT:
                raise ValueError("cache_assets.txt exceeds the asset-count limit")
            if any(not is_safe_relative_path(path) for path in cache_paths):
                raise ValueError("cache_assets.txt contains an unsafe asset path")
            if any(len(path.encode("utf-8")) > MAX_CACHE_PATH_BYTES for path in cache_paths):
                raise ValueError("cache_assets.txt contains an overlong asset path")
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
            undeclared_managed_assets = {
                name for name in names
                if name.startswith("assets/")
                and name != "assets/cache_assets.txt"
                and not name.startswith("assets/qml/")
                and not name.endswith("/")
                and name not in declared_assets
            }
            if undeclared_managed_assets:
                raise ValueError(
                    "package contains assets outside cache_assets.txt: "
                    + ", ".join(sorted(undeclared_managed_assets)[:5])
                )
            unexpected_qml_assets = {
                name for name in names
                if name.startswith("assets/qml/")
                and not name.endswith("/")
                and not any(
                    PurePosixPath(name[len("assets/"):]).is_relative_to(root)
                    for root in qml_asset_roots
                )
            }
            if unexpected_qml_assets:
                raise ValueError(
                    "package contains QML outside declared module roots: "
                    + ", ".join(sorted(unexpected_qml_assets)[:5])
                )
            if cache_content_digest(archive, cache_manifest_entry, cache_paths) != cache_lines[0]:
                raise ValueError("cache_assets.txt content digest does not match packaged assets")
            digest_verified_entries = {cache_manifest_entry} | {
                cached_asset_entry(cache_manifest_entry, path) for path in cache_paths
            }
            for entry in sorted(raw_archive_names):
                entry_info = archive.getinfo(entry)
                if entry_info.is_dir():
                    if entry_info.file_size != 0:
                        raise ValueError("package directory entry contains file data")
                    continue
                if entry not in digest_verified_entries:
                    verify_entry_integrity(archive, entry)
    except ElementTree.ParseError:
        print("ERROR: Phone package dependency declaration is invalid", file=sys.stderr)
        return 1
    except UnicodeError:
        print("ERROR: Phone package cache manifest is not valid UTF-8", file=sys.stderr)
        return 1
    except zipfile.BadZipFile:
        print("ERROR: Android phone package ZIP data is invalid", file=sys.stderr)
        return 1
    except OSError:
        print("ERROR: could not read Android phone package input", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"ERROR: incomplete Android phone package: {error}", file=sys.stderr)
        return 1

    print(f"Android package contents are complete ({len(declared_assets)} declared assets present).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
