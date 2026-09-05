# Test Overte for Android phones

## Device-free host tests

```bash
cd android/phone
./tests/phone-static-regression-test.sh
```

The host gate uses source, unit, contract, JavaScript, Java, and mock-ADB checks.
It does not prove an APK build or physical runtime behavior.

## Emulator

```bash
cd android/phone
./phone-emulator-test.sh all
```

This builds a separate x86_64 variant, boots the selected AVD, and runs AndroidX
instrumentation. See
[`android/phone/docs/EMULATOR_TESTS.md`](../../../android/phone/docs/EMULATOR_TESTS.md).

## Physical phone

```bash
cd android/phone
ANDROID_SERIAL=<serial> ./tests/phone-device-test.sh
```

The test validates the APK and target before installation, exercises bounded
lifecycle and deep-link behavior, and records only aggregate diagnostics. Test
at least one Adreno and one Mali device. Emulator evidence cannot replace
physical 4-KiB/16-KiB, graphics, audio, thermal, battery, cutout, or vendor
validation.

The wider test policy is in
[`android/common/docs/ANDROID_TESTING.md`](../../../android/common/docs/ANDROID_TESTING.md).

## Semantic tablet E2E

The checked-in Android Phone policy is
[`tests/device/policies/android-phone-flat-touch.json`](../../../tests/device/policies/android-phone-flat-touch.json).
It is evaluated independently from the Appium observation and requires
Tablet Home, Settings, General, Audio and Security while forbidding Controller,
HMD and VR render-resolution controls.

First audit the physical debug APK's UiAutomator2 tree as described in
[`tests/device/adapters/appium/README.md`](../../../tests/device/adapters/appium/README.md).
Enable `controls.tablet.semanticUi` in the protected target configuration only
when the semantic QML object names are exposed as actionable native IDs. Then
run:

```bash
python3 tests/device/run.py \
  --adapter-manifest tests/device/adapters/appium/android.json \
  --catalog tests/device/catalog.json --suite tablet-e2e \
  --tablet-policy tests/device/policies/android-phone-flat-touch.json \
  --output-dir /tmp/overte-android-phone-tablet-e2e --require-complete
```

The acceptance sequence keeps one process alive, observes stable ready screens,
uses real element clicks, returns through visible semantic navigation controls,
and verifies forbidden features only after readiness. Raw Accessibility XML and
screenshots are opt-in diagnostics; inspect and redact them before retention.
