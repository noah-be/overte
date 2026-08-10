# Test Overte for Android phones

## Device-free host tests

```bash
cd android
./tests/phone-static-regression-test.sh
```

The host gate uses source, unit, contract, JavaScript, Java, and mock-ADB checks.
It does not prove an APK build or physical runtime behavior.

## Emulator

```bash
cd android
./phone-emulator-test.sh all
```

This builds a separate x86_64 variant, boots the selected AVD, and runs AndroidX
instrumentation. See
[`android/ANDROID_PHONE_EMULATOR_TESTS.md`](../../../android/ANDROID_PHONE_EMULATOR_TESTS.md).

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
