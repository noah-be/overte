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
  `apps/phoneInterface/src/emulator/res/values/`;
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

## Requirements

- the same SDK, NDK, CMake, Conan, Python, Perl, and JDK requirements as the
  Phone build;
- an existing x86_64 AVD (default: `overte_api35`);
- working KVM acceleration;
- enough space for the first Qt, libnode, dependency, and application builds.

Select another AVD with `PHONE_EMULATOR_AVD=<name>`. The runner uses a private
Gradle temporary directory below `android/build/phone-emulator`, so it does not
depend on writable capacity in a host `/tmp` quota.

## Commands

Run from `android/`:

```bash
./phone-emulator-test.sh doctor
./phone-emulator-test.sh deps
./phone-emulator-test.sh build
./phone-emulator-test.sh start
./phone-emulator-test.sh test
./phone-emulator-test.sh stop
```

The complete workflow is:

```bash
./phone-emulator-test.sh all
```

`all` builds and tests. The emulator is stopped only by the explicit `stop`
command, which makes repeated local test runs faster. Build parallelism can be
limited with `PHONE_BUILD_JOBS=<count>`.

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
`apps/phoneInterface/build/reports/androidTests/connected/emulator/`.

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

1. Extend the cold-launch test with bounded failure diagnostics and repeat it
   ten times to establish its flake-free emulator baseline.
2. Cover the first high-value UI flows: permission denial and Settings recovery,
   login or serverless entry,
   opening and closing the Tablet, settings, deep links, and Activity restart.
3. Capture filtered logcat, a screenshot, Activity/window state, and native
   crash or tombstone hints automatically whenever a device test fails.
4. Record cold and warm build times. Evaluate `ccache`, persistent Conan and
   Gradle caches, AVD snapshots, and the cost of the generated render-pipeline
   translation unit.
5. Add an optional CI job that runs `phone-emulator-test.sh all`. Publish or
   restore prebuilt Conan packages so CI does not rebuild Qt for every run.
6. Audit and clean the host `/tmp` quota separately so older regression tests
   that hard-code `/tmp` can run again.
