# Android Phone APK size comparison

Experimental branch based on the R8 candidate, not a replacement for the published
0.1.0 reference or the F-Droid inclusion request. Both candidates use 0.1.1 (2) for
comparison; their source commits and separate CI artifacts identify them.

Changes in this variant:

- Only the F-Droid Phone target profile selects `libnode/*:build_type=Release`.
  Other dependency settings and source recipe versions stay the same. Normal
  Phone/Pico profiles and iOS are untouched. The profile's integrity binding is
  updated. This is a build-mode experiment requiring script-engine/device testing.
- Phone shader QRC chunks are combined into one resource pool, then the Qt-generated
  C++ data is compacted. Identical payloads share offsets. Every shader alias,
  reflection payload, locale, timestamp and registration function is preserved.
  No shader code is rewritten and no shader variant is removed.
- The external Phone resources.rcc uses the same lossless compaction. No media,
  font, avatar, animation or offline environment is removed or re-encoded.
- Qt Creator `designer/` panels are excluded from both packaged QML representations.
  Runtime QML and both loader paths remain. These are editor integration resources,
  not Phone UI panels.
- The unsigned F-Droid APK is recompressed at deflate level 9, retaining every ZIP
  payload, entry order, compression method, timestamp and external attributes. It
  is realigned with the SDK's zipalign (`-P 16`, alignment 4) and checked again.
  The result replaces the original only if smaller. Signed APKs are rejected.

The compactor only accepts Qt format version 3; unsupported layouts fail the build.
It verifies every payload and lookup metadata before writing. It neither patches
Qt nor adds an application runtime dependency. Combining shader resources can
increase peak compilation memory for that one translation unit.

## Regression checks

```sh
python3 android/phone/tests/phone-resource-compaction-test.py --qt-root /path/to/native/qt/package
# Optional: also compare all resources of an existing APK through real Qt lookups:
python3 android/phone/tests/phone-resource-compaction-test.py --qt-root /path/to/native/qt/package --apk /path/to/baseline.apk
python3 android/phone/tests/phone-apk-repack-test.py
bash android/phone/tests/phone-shader-payload-test.sh
bash android/phone/tests/phone-release-config-test.sh
python3 android/phone/fdroid/conan/test_reproducible_graph.py
python3 android/phone/fdroid/submission/test_submission.py
```

The Qt test uses actual Qt 5 rcc, C++ compilation and QFile lookups: compressed and
uncompressed resources, aliases, directories, empty/binary contents and localized
entries. It also executes the changed CMake shader-resource block with two chunks
and compiles the resulting library. The F-Droid adapter runs the Qt test with its
fresh source-built host Qt and runs APK repack tests before compiling the app.
The optional full baseline test verified all 1,137 resource paths/content hashes.
Qt resource flags and ZIP payload checks run again on actual build outputs.

## Acceptance remains separate

Compare actual APK/entry sizes against the R8-only artifact. Require successful
APK inspection and native alignment checks. Test launch, QML UI, script loading,
world rendering, movement, audio and offline startup on the Phone before promoting
this experiment. A successful compiler run alone is not runtime compatibility or
reproducibility evidence. Another independent build/signature comparison is needed
if this candidate is selected for the reproducible F-Droid release.
