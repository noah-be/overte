# Android Phone continuous integration

The active product branch is `android-phone`; the retired
`feature/android-phone-support` branch must not be used.

- `Android tests` provides device-free host and contract gates.
- `Android Phone trusted build` is manual and accepts `android-phone` or an
  immutable Phone alpha tag on the isolated build runner.
- `Android Phone release candidate` produces an unsigned, store-neutral,
  locally inspectable candidate from an immutable tag.
- `Android Phone emulator acceptance` validates the exact tagged source through
  a separate x86_64 instrumentation graph; it cannot install the ARM64 candidate
  APK on that emulator.

Runner isolation, protected environments, artifact names, retention, and local
contract commands are detailed in
[`android/phone/docs/ANDROID_PHONE_CI_CD.md`](../../../android/phone/docs/ANDROID_PHONE_CI_CD.md)
and
[`android/phone/docs/ANDROID_PHONE_RELEASE_OPERATIONS.md`](../../../android/phone/docs/ANDROID_PHONE_RELEASE_OPERATIONS.md).
