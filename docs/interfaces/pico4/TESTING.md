# Test Overte for Pico 4

## Device-free tests

From the repository root:

```bash
./android/tests/pico-device-free-test.sh
```

This checks shell, packaging, WebView, microphone, OpenXR lifecycle, fixture,
device-lock, and power-analysis contracts without ADB or a headset. The broader
hardware-independent suite is documented in
[`android/docs/PICO4_TESTING.md`](../../../android/docs/PICO4_TESTING.md).

## Physical headset

Build verification and device mutation are separate. The device-acceptance
workflow requires an immutable candidate, explicit installation confirmation, a
protected environment, and a dedicated runner with exactly one authorized Pico.
It binds the report to the tag, commit, APK digest, and signing certificate.

A device-free pass cannot establish rendering, controller, audio, thermal,
power, lifecycle, or comfort behavior on a worn headset.
