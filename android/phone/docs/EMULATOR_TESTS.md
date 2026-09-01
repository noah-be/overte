# Android Phone emulator tests

This document describes the local, hardware-accelerated Android emulator test
path for `phoneInterface`. It is separate from the ARM64 production Phone
build: the emulator variant and all of its native dependencies use x86_64.

## Implemented setup

The setup consists of:

- the Conan profile `conan/profiles/phone-emulator-x86_64` for Android API 26,
  NDK 27.3, Clang 18, Debug, and x86_64;
- `prepare-phone-emulator-deps.sh`, which builds the host shader tools and the
  x86_64 target dependency graph, verifies the Qt ABI, and writes an atomic
  readiness sentinel only after the graph is complete;
- an isolated Gradle `emulator` build type selected by
  `PHONE_EMULATOR_BUILD=1`; normal Phone debug and release builds remain
  ARM64-only;
- x86_64 Qt loader resources under
  `phone/apps/phoneInterface/src/emulator/res/values/`;
- `phone-emulator-test.sh`, which checks the host, builds, starts an existing
  x86_64 AVD headlessly with KVM, disables animations, runs instrumentation,
  and stops the AVD on request;
- AndroidX instrumentation smoke tests that verify the target package, the
  emulator ABI, the packaged x86_64 `libphoneInterface.so`, and a real cold
  transition from `PermissionsActivity` into the Qt/native Activity without
  intercepting its Intent;
- static configuration checks in `tests/phone-emulator-config-test.sh`, also
  included in the Phone static regression suite.

Supporting native build changes allow libnode to cross-compile for Android
x86_64, use Conan's Draco target when available, omit Breakpad when explicitly
disabled, and compile the audio SIMD sources with their required x86 flags.
Generated Conan outputs are ignored and remain reproducible local artifacts.
The emulator build also disables the Debug variant's offline JaCoCo
instrumentation: without the matching runtime it instruments QtApplication and
crashes before AndroidJUnitRunner starts. Debug coverage itself remains
unchanged.

Qt Location remains enabled, but the embedded Mapbox GL backend is disabled in
the emulator profile because its bundled Boost/Mapbox sources do not compile
with the selected NDK and C++17 toolchain. The OSM/Qt Location API path remains
available.

The x86_64 product requests GLES 3.1 because the Android Emulator does not
expose GLES 3.2. Optional 3.2 entry points use their GLES extension equivalents
or are skipped when unavailable; ARM64 Phone builds keep the GLES 3.2 path.

## Requirements

- the same SDK, NDK, CMake, Conan, Python, Perl, and JDK requirements as the
  Phone build;
- an existing x86_64 AVD (default: `overte_api35`);
- working KVM acceleration;
- enough space for the first Qt, libnode, dependency, and application builds.

Select another AVD with `PHONE_EMULATOR_AVD=<name>`. The runner uses a private
Gradle temporary directory below `android/phone/build/phone-emulator`, so it
does not depend on writable capacity in a host `/tmp` quota.

## Choose the test path

There are two useful emulator workflows. They answer different questions:

| Workflow | Native rebuild | What it proves |
| --- | --- | --- |
| Prebuilt APK smoke test | No | The AVD boots, accepts the APK, starts the Java/Qt/native loader, and produces usable lifecycle and crash diagnostics |
| x86_64 instrumentation | Yes, on the first run | The emulator-specific application and test APKs build and the AndroidX device suite passes |

The prebuilt smoke test is the quickest way to check a workstation when no
physical phone is available. It cannot run the repository's AndroidX tests:
release downloads contain the application APK, but not the separately built
instrumentation APK. Use the x86_64 workflow for a passing functional emulator
gate.

### Prebuilt Alpha 4 smoke test without rebuilding

[Android Phone Alpha 4](https://github.com/noah-be/overte/releases/tag/android-phone-v0.1.0-alpha.4)
is a signed, ARM64-only debug APK. Download and verify the exact release asset:

```bash
apk_dir="${XDG_CACHE_HOME:-$HOME/.cache}/overte/android-phone-alpha4"
apk="$apk_dir/Overte-Android-Phone-0.1.0-alpha.4-arm64-debug.apk"
mkdir -p "$apk_dir"
gh release download android-phone-v0.1.0-alpha.4 \
    --repo noah-be/overte \
    --pattern 'Overte-Android-Phone-0.1.0-alpha.4-arm64-debug.apk' \
    --dir "$apk_dir" --clobber
printf '%s  %s\n' \
    1ecf19b0cc65dea3cf9a02906412660dfe48b41dfb76720996d766ce4e9069fb \
    "$apk" | sha256sum --check
```

Set the SDK path and run the repository helper from `android/`. `start` only
boots the existing AVD; it does not compile Overte or its dependencies:

```bash
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}"
adb="$ANDROID_SDK_ROOT/platform-tools/adb"

cd android
./phone/phone-emulator-test.sh doctor
./phone/phone-emulator-test.sh start
serial="$(<phone/build/phone-emulator/serial)"
```

Alpha 4 can run on an x86_64 AVD only when its system image includes ARM64
binary translation. Check the APK and guest before installation:

```bash
"$ANDROID_SDK_ROOT/build-tools/36.0.0/aapt2" dump badging "$apk" \
    | grep "native-code"
"$adb" -s "$serial" shell getprop ro.product.cpu.abilist
"$adb" -s "$serial" shell getprop ro.dalvik.vm.native.bridge
```

The APK reports `arm64-v8a`. Continue only if the guest ABI list also includes
`arm64-v8a`; the tested Google APIs image reports `libndk_translation.so` as its
native bridge. Images without translation reject the install with
`INSTALL_FAILED_NO_MATCHING_ABIS`.

Install, bypass the optional microphone prompt, clear old logs, and cold-start
the real launcher:

```bash
"$adb" -s "$serial" install -r "$apk"
"$adb" -s "$serial" shell pm grant \
    org.overte.phone android.permission.RECORD_AUDIO
"$adb" -s "$serial" logcat -c
"$adb" -s "$serial" shell am force-stop org.overte.phone
"$adb" -s "$serial" shell am start -W -S \
    -n org.overte.phone/org.overte.phone.PermissionsActivity

sleep 20
"$adb" -s "$serial" shell pidof org.overte.phone
"$adb" -s "$serial" shell dumpsys activity activities \
    | grep -m1 'topResumedActivity\|mResumedActivity'
"$adb" -s "$serial" logcat -b crash -d -v brief
```

An empty `pidof` result or a different resumed Activity means the application
did not survive the smoke window. Always inspect the crash buffer; a successful
`adb install` and `Status: ok` from Activity Manager do not prove that Qt or the
renderer remained alive. Clean up explicitly when finished:

```bash
"$adb" -s "$serial" uninstall org.overte.phone
./phone/phone-emulator-test.sh stop
```

#### Result on the tested workstation

On 2026-08-13, Emulator 37.1.11 booted the `overte_api35` Google APIs x86_64
AVD with KVM and the NVIDIA host renderer. The image advertised
`x86_64,arm64-v8a`, so Alpha 4 installed successfully. Android loaded
`libphoneInterface.so` through `libndk_translation.so`, Qt started, and
`PhoneInterfaceActivity` reached `RESUMED` after approximately 2.8 seconds.

This is not a passing application smoke test. After approximately 14 seconds,
the process aborted with `Failed to create OffscreenGLCanvas context`. The AVD
exposed OpenGL ES 3.1, while the ARM64 production APK requests OpenGL ES 3.2.
The result proves that the installed emulator, KVM, ADB, ARM translation, APK
installation, and early native loader path work; it also proves that this
production APK cannot replace the dedicated emulator build for graphics or
functional testing on this AVD.

### Fedora and SwiftShader troubleshooting

On one Fedora 44 workstation, Android Emulator 36.6.11 and 37.1.11 exited with
signal 11 while executing SwiftShader JIT code. The failure was reproduced with
API 35 and API 36 x86_64 images and with both SwiftShader and Lavapipe software
renderers. KVM acceleration and the Android images continued to work with the
NVIDIA host renderer, so this is a host-specific troubleshooting result rather
than a general Fedora limitation.

`phone-emulator-test.sh` already selects `-gpu host`. When starting an AVD
manually on an affected workstation, also select the host renderer instead of
`-gpu software`. Record the emulator version, acceleration result, and verbose
startup output before changing images or recreating the AVD:

```bash
emulator -version
emulator -accel-check
emulator -avd overte_api35 \
    -no-window -no-audio -gpu host -no-snapshot -wipe-data -verbose
```

This workaround depends on a functioning host GPU driver. Do not generalize it
to headless CI machines without first validating their renderer and emulator
combination.

The host renderer also needs access to the desktop graphics session. If the
emulator log contains `Failed to get EGL display`, run it from a terminal opened
inside the desktop session and confirm that `DISPLAY` and `XAUTHORITY` are set.
This was required on the validated GNOME/Xwayland workstation; it is separate
from the KVM acceleration check.

## Commands

Run from `android/`:

```bash
./phone/phone-emulator-test.sh doctor
./phone/phone-emulator-test.sh deps
./phone/phone-emulator-test.sh build
./phone/phone-emulator-test.sh start
./phone/phone-emulator-test.sh test
./phone/phone-emulator-test.sh stop
```

The complete workflow is:

```bash
./phone/phone-emulator-test.sh all
```

`all` builds and tests. The emulator is stopped only by the explicit `stop`
command, which makes repeated local test runs faster. Build parallelism can be
limited with `PHONE_BUILD_JOBS=<count>`.

To reproduce an intermittent instrumentation failure without repeatedly running
the complete device suite, select one fully-qualified test class (or one
`Class#method`) and a bounded repetition count:

```bash
PHONE_EMULATOR_TEST_CLASS=org.overte.phone.PhoneColdLaunchInstrumentedTest \
PHONE_EMULATOR_TEST_REPETITIONS=10 \
    ./phone/phone-emulator-test.sh test
```

The repetition count must be between 1 and 25. Counts above one require a class
filter, preventing an accidental expensive repetition of the complete suite.
Every attempt is forced through Gradle even when its inputs are unchanged.

If instrumentation fails, the runner stops at that attempt and prints the path
to a diagnostic directory below `build/phone-emulator/diagnostics/`. It contains
the complete Gradle/instrumentation output, general and crash-buffer logcat,
Activity state, Android native-crash DropBox output, and the available tombstone
listing. Diagnostic collection is best-effort and never hides the original test
exit status.

## Validated baseline

The initial implementation was validated locally with the `overte_api35` API
35 x86_64 AVD. The complete native application and both APKs built, Android
installed the application and test packages, and AndroidJUnitRunner reported
the complete current device suite as passing:

```text
tests="9" failures="0" errors="0" skipped="0"
```

This includes
`EmulatorPackagingTest.emulatorRunsX86_64PackageWithNativeInterface`, the
Phone deep-link tests, and the Permissions activity intent tests. The latter
use a negative `hasExtra` matcher that also handles intents whose extras bundle
is absent. The generated test report is located below
`phone/apps/phoneInterface/build/reports/androidTests/connected/emulator/`.

The emulator configuration test, Phone release configuration test, shell
syntax checks, and Git whitespace checks also passed. Some older regression
helpers create temporary files directly in `/tmp`; those require free host
quota independently of this emulator runner.

The subsequent cold-launch instrumentation test grants the optional microphone
permission, starts the real launcher with a cleared task, waits up to 30 seconds
for `PhoneInterfaceActivity` to reach `RESUMED`, and requires it to remain
resumed through a short stability window. Unlike the intent-policy tests it
does not stub the destination Activity, so a loader, packaged-library, asset
extraction, Qt initialization, or immediate native-startup failure fails the
instrumentation process. Run the emulator suite again to establish the updated
device count after this test is merged; the historical nine-test baseline above
is retained as the evidence for the initial emulator implementation.

## Recommended next steps

1. Run the cold-launch instrumentation class repeatedly to establish its
   flake-free emulator baseline.
2. Cover the first high-value UI flows: permission denial and Settings recovery,
   login or serverless entry,
   opening and closing the Tablet, settings, deep links, and Activity restart.
3. Add a screenshot and narrower package-specific log filtering to the automatic
   failure diagnostics where they improve investigations.
4. Record cold and warm build times. Evaluate `ccache`, persistent Conan and
   Gradle caches, AVD snapshots, and the cost of the generated render-pipeline
   translation unit.
5. Add an optional CI job that runs `phone-emulator-test.sh all`. Publish or
   restore prebuilt Conan packages so CI does not rebuild Qt for every run.
6. Audit and clean the host `/tmp` quota separately so older regression tests
   that hard-code `/tmp` can run again.
