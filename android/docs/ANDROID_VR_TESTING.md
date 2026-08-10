# Android VR Hardware-Free Test Gate

The shared standalone Android-VR integration gate is:

```bash
cd android
tests/run-tests.sh android-vr
```

It is intended for changes entering `android-vr` or affecting both a headset
product and shared Android code. It requires no connected headset, Android SDK,
NDK, Conan graph, APK, signing key, or store account.

## Gate contents

The catalog selects exactly six suites:

1. tracked Android Bash syntax;
2. tracked Android Python syntax;
3. Android module, manifest-security, and runtime-boundary inventory;
4. native host policies, including the seven current OpenXR policy executables;
5. sixteen Pico runtime tests covering entry points, WebView, audio, OpenXR,
   interaction, tablet/Create behavior, and world state;
6. the real Interface, Phone, Pico, and Quest launcher policies under Robolectric.

The Pico child suite remains authoritative for Pico packaging, APK verification,
release metadata, performance policy, power tooling, unattended/device tooling,
and hardware acceptance. The Android-VR parent gate deliberately does not duplicate
those vendor responsibilities.

## Output and expected runtime

The command atomically publishes the stable aggregate report:

```text
android/build/test-results/suite/TEST-android-android-vr.xml
```

The aggregate always contains six top-level test cases, one per catalog suite. A
partial or interrupted run leaves a failing incomplete report instead of stale
success. Native CTest and Robolectric also retain their granular reports below
`android/build/test-results/native` and `android/tests/robolectric/build/test-results`.
The focused native report is named `TEST-native-android-vr.xml` and contains exactly
the seven OpenXR policy cases selected through CTest's `android-vr` label.

On a prepared workstation the gate normally completes in under one minute. A clean
host can take several minutes while the pinned Gradle/Robolectric dependencies are
restored. The catalog limits the Pico runtime subset to five minutes; CI limits the
complete command to fifteen minutes and leaves five minutes for report upload.

## CI scope

`.github/workflows/android-vr-tests.yml` runs one job for relevant pull requests,
the `android-main` and `android-vr` integration branches, Android-VR child branches,
and the current boundary-refactoring branch. This adds one parent integration gate
without cloning the Phone or Pico build/release workflows.

Passing this gate proves deterministic source and host-policy contracts only. It
does not prove APK construction, OpenXR runtime compatibility, tracking, rendering,
controllers, microphone capture, thermals, or world usability on real hardware.
