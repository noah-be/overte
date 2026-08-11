# Legacy GVR removal evidence

The legacy Interface no longer declares or links Google VR. The previous build
mixed unresolved Maven artifacts at version 1.80.0 with an unused prebuilt
acquisition path at version 1.101.0. No active source references GVR symbols.

After producing a real arm64 Interface APK, verify the packaged result with:

```bash
python3 android/vr/quest/tests/legacy-gvr-evidence.py path/to/interface.apk \
  --readelf "$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf"
```

The JSON report records packaged GVR library hashes, `DT_NEEDED` entries and
undefined `gvr_*` symbols from `libnative-lib.so`. A successful post-removal
check must report no packaged GVR libraries, no GVR dependency and no undefined
GVR symbol.

This evidence applies only to the inspected APK and ABI. It is not a runtime
smoke test, SBOM or proof for other ABIs. If the remaining legacy dependencies
cannot be resolved, the static dependency contract still proves that the dead
GVR acquisition, Gradle declarations and native link have been removed, but a
rebuilt-APK check remains pending.
