# Legacy GVR evidence

Before changing the legacy Interface GVR dependencies, inspect a real arm64 APK:

```bash
python3 tests/legacy-gvr-evidence.py path/to/interface.apk \
  --readelf "$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf"
```

The JSON report records packaged GVR library hashes, `DT_NEEDED` entries and
undefined `gvr_*` symbols from `libnative-lib.so`. `supportsRemoval` is evidence
only for that APK and ABI. It is not a build, runtime smoke test, SBOM or proof
for other ABIs. GVR removal still requires a rebuilt APK and a device- or
emulator-level smoke test.
