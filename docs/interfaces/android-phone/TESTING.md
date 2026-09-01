# Test Overte for Android phones

## Device-free host tests

```bash
cd android
./tests/phone-static-regression-test.sh
```

The host gate uses source, unit, contract, JavaScript, Java, and mock-ADB checks.
It does not prove an APK build or physical runtime behavior.

## Emulator

For a no-build workstation smoke test, use a prebuilt APK. The tested Alpha 4
APK installs on the `overte_api35` x86_64 Google APIs image because that image
includes ARM64 binary translation. It reaches the real Qt/native Activity, but
then aborts in `OffscreenGLCanvas`; the production APK requires OpenGL ES 3.2
while the AVD exposes 3.1. This path verifies the emulator setup and
diagnostics; it is not a passing functional test and cannot run the AndroidX
suite without its separate test APK.

For the complete x86_64 instrumentation workflow:

```bash
cd android
./phone/phone-emulator-test.sh all
```

This builds a separate x86_64 variant, boots the selected AVD, and runs AndroidX
instrumentation. See
[the complete emulator guide](../../../android/phone/docs/EMULATOR_TESTS.md) for
the tested prebuilt-APK commands, full instrumentation path, expected results,
and troubleshooting.

## Physical phone

```bash
cd android
ANDROID_SERIAL=<serial> ./tests/phone-device-test.sh
```

The test validates the APK and target before installation, exercises bounded
lifecycle and deep-link behavior, and records only aggregate diagnostics. Test
at least one Adreno and one Mali device. Emulator evidence cannot replace
physical 4-KiB/16-KiB, graphics, audio, thermal, battery, cutout, or vendor
validation.

The wider test policy is in
[`android/docs/ANDROID_TESTING.md`](../../../android/docs/ANDROID_TESTING.md).
