#!/usr/bin/env python3

import sys
import zipfile


REQUIRED_ENTRIES = {
    "AndroidManifest.xml",
    "classes.dex",
    "assets/cache_assets.txt",
    "assets/resources.rcc",
    "assets/android_rcc_bundle.rcc",
    "lib/arm64-v8a/libphoneInterface.so",
    "lib/arm64-v8a/libQt5PositioningQuick_arm64-v8a.so",
    "lib/arm64-v8a/libcrypto_1_1.so",
    "lib/arm64-v8a/libssl_1_1.so",
    "lib/arm64-v8a/libplugins_audio_qtaudio_opensles_arm64-v8a.so",
    "lib/arm64-v8a/libplugins_bearer_qandroidbearer_arm64-v8a.so",
    "lib/arm64-v8a/libplugins_imageformats_qjpeg_arm64-v8a.so",
    "lib/arm64-v8a/libplugins_imageformats_qsvg_arm64-v8a.so",
    "lib/arm64-v8a/libplugins_platforms_qtforandroid_arm64-v8a.so",
}


def main():
    if len(sys.argv) != 2:
        print("Usage: check-phone-apk-contents.py <apk>", file=sys.stderr)
        return 2
    try:
        with zipfile.ZipFile(sys.argv[1]) as archive:
            names = set(archive.namelist())
            missing = REQUIRED_ENTRIES - names
            if missing:
                raise ValueError("missing required entries: " + ", ".join(sorted(missing)))

            cache_lines = archive.read("assets/cache_assets.txt").decode("utf-8").splitlines()
            if len(cache_lines) < 2 or not cache_lines[0].isdigit():
                raise ValueError("invalid cache_assets.txt header")
            declared_assets = {"assets/" + line for line in cache_lines[1:] if line}
            missing_assets = declared_assets - names
            if missing_assets:
                preview = ", ".join(sorted(missing_assets)[:5])
                raise ValueError(
                    f"{len(missing_assets)} cache assets are absent" +
                    (f" (first: {preview})" if preview else "")
                )
    except (OSError, UnicodeError, ValueError, zipfile.BadZipFile) as error:
        print(f"ERROR: incomplete Android phone APK: {error}", file=sys.stderr)
        return 1

    print(f"APK contents are complete ({len(declared_assets)} declared assets present).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
