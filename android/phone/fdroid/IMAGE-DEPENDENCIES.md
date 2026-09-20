# Android image dependency security update

The F-Droid source-build graph pins libpng 1.6.58 and OpenEXR 3.2.11.
OpenEXR 3.2 requires libdeflate; its source is pinned to 1.25, using the
Conan Center recipe from commit `319023a7b852a005e96a38919588263b05a9d541`.
The source closure records archive and license hashes for all three libraries.

libpng remains on its existing 1.6 API. OpenEXR uses the maintained 3.2
security branch to avoid a larger API migration. These changes address the
outdated image-decoder dependencies found in the Android APK review; they do
not claim to resolve unrelated scanner findings.

Sources:

- [libpng release and security notes](https://www.libpng.org/pub/png/libpng.html)
- [OpenEXR security release notes](https://openexr.com/en/latest/news.html)
- [OpenEXR 3.2.11 source](https://github.com/AcademySoftwareFoundation/openexr/releases/tag/v3.2.11)

The shared Pico recipe retains its `openexr/3.1.9` default. Only the Phone
F-Droid subclass overrides that value; iOS and the normal Pico graph are not
upgraded. Phone's Qt recipe pins the new libpng for both Android and the Linux
host tools used to build Android.

Run the lock/source-store regression checks with:

```sh
python3 -B -m unittest discover -s android/phone/fdroid/conan -p 'test_*.py'
```

`test_image_dependency_versions.py` guards against reverting either decoder,
losing the hash-bound sources, or changing Pico's default. The existing graph,
recipe-export, and source-closure tests validate the linked lock metadata.
Compilation and APK validation are separate requirements; these unit tests
alone do not qualify a release.
