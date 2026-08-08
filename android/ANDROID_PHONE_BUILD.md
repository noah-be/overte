# Build Overte for Android phones

> [!CAUTION]
> **Experimental AI-assisted port**
>
> The phone client is an early development port. It has not yet received the
> device coverage, security review, performance validation, or release testing
> expected of a production application. Review changes before using the client
> with valuable accounts or publishing its APK.

The `phoneInterface` module packages Overte's normal mono 2D renderer and
touchscreen input for 64-bit Android phones. It deliberately has its own
application ID (`org.overte.phone`) and does not package the Pico OpenXR
runtime. The port currently targets landscape-oriented, ARM64 devices running
Android 8 (API 26) or newer and targets Android 16 (API 36).

Run the commands in this document from the repository's `android/` directory.

## Current scope

The first development milestone provides:

- an independent Android application and launcher;
- Overte's Qt-based client and 2D OpenGL display path;
- touchscreen and virtual-pad input from the existing Interface code;
- network access, audio output, optional microphone permission, and vibration;
- the same pinned Android/Qt/Conan toolchain used by the Pico port.

The microphone permission is requested at startup, but denying it does not
block access to a world. Portrait mode, 32-bit devices, store publication, and
broad phone/GPU compatibility are outside this first milestone.

> [!IMPORTANT]
> The phone APK must use the dedicated, verified 16 KiB Qt and Conan outputs.
> The build fails closed when those outputs are absent, incomplete, changed
> since verification, or still contain a 4 KiB-aligned ELF segment. Do not use
> the shared legacy Pico dependency graph for a distributable phone APK.

## Requirements

The phone build currently shares the Pico Android dependency set and therefore
has the same host requirements:

- 64-bit Linux;
- JDK 17 through 21;
- Android SDK Platform 36 and Build-Tools 36.0.0;
- Android NDK `27.3.13750724`;
- CMake 3.31.6, Ninja, Conan 2, Python, Perl, and Git;
- ADB for installation on a phone.

Android Studio is optional. By default the scripts look for the SDK in
`ANDROID_SDK_ROOT`, then `ANDROID_HOME`, then `$HOME/Android/Sdk`.

Inspect the environment without downloading dependencies or changing it:

```bash
./build-phone.sh doctor
```

The doctor command uses the established Pico environment checker because both
applications intentionally use the same toolchain versions.

## First setup and required 16 KiB build order

The phone build uses the same pinned dependency sources and recipes as the
Pico build, but its native libraries must be rebuilt into dedicated 16 KiB
outputs. Run these phases in order:

The two long dependency helpers require at least 32 GB (decimal) of configured
swap before they change build outputs. They always use 16 build jobs and
restart themselves in a systemd user scope with `MemoryMax=20000000000`
(exactly 20 GB decimal). The active
cgroup limit is verified after restart. A host without systemd user scopes, a
smaller swap allocation, or an unverifiable memory limit therefore stops
before the dependency build; there is intentionally no unbounded fallback.

1. Populate the dependency/source cache. On a new machine, explicitly allow
   the large download:

   ```bash
   ./build-pico.sh deps --download
   ```

2. Rebuild Qt for 16 KiB pages. This is the longest dependency build:

   ```bash
   ./build-phone-qt-16k.sh
   ```

3. Rebuild the non-Qt dependencies. The script verifies the complete Qt and
   non-Qt graph and publishes the content-bound readiness marker only after
   successful verification:

   ```bash
   ./prepare-phone-16k-conan-deps.sh
   ```

4. Build the APK from the verified graph:

   ```bash
   ./build-phone.sh build
   ```

Do not use `./build-phone.sh setup --download` as a substitute for this first
16 KiB setup sequence: that convenience command prepares the shared dependency
cache and then proceeds directly to the fail-closed APK build. Once the
dedicated outputs and readiness marker exist, normal `build`, `install`, and
`deploy` commands can be used as described below.

## Development commands

| Command | Purpose |
| --- | --- |
| `./build-phone.sh doctor` | Inspect the shared Android build environment |
| `./build-phone.sh prepare` | Restage already available Qt/Conan dependencies |
| `./build-phone.sh build` | Build the debug APK from verified 16 KiB dependencies |
| `./build-phone.sh` | Prepare dependencies and build the debug APK |
| `./build-phone.sh install` | Install and start an already built APK |
| `./build-phone.sh deploy` | Prepare, build, install, and start the app |
| `./build-phone.sh setup --download` | Populate the shared cache, prepare, and attempt a build |
| `./build-phone.sh --help` | Show the command summary |

Limit native compilation parallelism performed through `build-phone.sh` when
memory is constrained:

```bash
PHONE_BUILD_JOBS=4 ./build-phone.sh
```

This setting is forwarded to the wrapper's prepare and CMake build phases. It
does not override the fixed 16-job count in the dedicated Conan 16 KiB
profiles. The long dependency helpers additionally enforce their documented
32 GB swap prerequisite and 20 GB decimal cgroup memory ceiling.

## Install on a phone

Enable developer options and USB debugging on the phone, connect it over USB,
and accept Android's authorization prompt. Confirm that ADB reports it as
`device`:

```bash
"${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}/platform-tools/adb" devices
```

Then build, install, and launch the client:

```bash
./build-phone.sh deploy
```

Installation never lets ADB choose an implicit default target. When exactly
one authorized non-Pico phone is connected it is selected unambiguously;
otherwise select the intended phone explicitly:

```bash
ANDROID_SERIAL=<serial> ./build-phone.sh deploy
```

`install` uses `adb install -r`, preserving existing application data. The
debug APK is written to:

```text
apps/phoneInterface/build/outputs/apk/debug/phoneInterface-debug.apk
```

## Static regression check

Run the lightweight host check after changing the module, manifest, or wrapper:

```bash
./tests/phone-host-regression-test.sh
```

It reads source files only. It does not invoke Gradle, build an APK, access the
network, use Git, or contact a device. The check verifies the structural
contract of the port: independent module wiring, ARM64/API settings, phone
application identity, launcher and Qt activities, required phone capabilities,
and wrapper commands.

## Architecture notes

`settings-phone.gradle` selects only `phoneInterface`, allowing the phone APK
to evolve independently of `picoInterface`. The module's native target links
the main Interface client. It consequently uses Overte's existing
`Basic2DWindowOpenGLDisplayPlugin` and touchscreen virtual-pad integration
instead of the Pico OpenXR display and tracked-controller plugins.

The Gradle module stages Qt plugins, QML plugins, OpenSSL libraries,
`resources.rcc`, compiled Interface resources, and scripts in the same way as
the proven Pico packaging. Android-specific Qt and TBB runtime overrides are
also shared for now. These are implementation dependencies, not an indication
that the phone APK requires Pico hardware or an OpenXR runtime.

At startup, `PermissionsActivity` handles the optional microphone permission
and transfers control to `PhoneInterfaceActivity`. The latter hosts the native
Qt client, unpacks its assets into the application cache, and keeps the display
awake while the client is active.

## Device validation checklist

A successful build is only the first gate. Before calling a change usable,
exercise it on at least one Adreno and one Mali device and record:

1. fresh install, launch, microphone accept and deny paths;
2. connection to a domain and visible 2D scene rendering;
3. movement, camera look, jump/action controls, and multi-touch;
4. audio input/output, Android keyboard, and login/navigation UI;
5. background/foreground transitions, screen rotation policy, and reconnects;
6. memory use, frame pacing, temperature, and battery drain over a long run.

Cutouts, gesture navigation, unusual DPI values, and vendor-specific power
management deserve explicit checks. Automated static validation cannot expose
these device/runtime problems.

Run the repeatable smoke test against an already built APK with an explicit
device serial. It installs the app, exercises launch, a fixed local test deep
link, and a background/foreground transition, and records aggregate crash and
16 KiB compatibility diagnostics in a temporary report directory:

```bash
ANDROID_SERIAL=<phone-serial> ./tests/phone-device-test.sh
```

Pass an APK path as the optional first argument. `PHONE_TEST_REPORT` may point
to an existing directory outside the Git worktree when reports should be
retained at a known location. Device diagnostics are refused inside the
repository. The summary contains only the app package, lifecycle status flags,
and aggregate test counts: it never records the device serial, model, deep-link
URI, account data, process IDs, or raw Android output. Logcat is restricted to
the tested app process and inspected only as a stream; package exit diagnostics
are likewise reduced immediately to a count. Neither raw source is written to
the report.
The script never uses ADB's implicit default device: without
`ANDROID_SERIAL`, it proceeds only if exactly one authorized non-Pico phone is
identifiable. It exits with status 2 when crash or page-size-mismatch log lines
are detected. The test changes device state by installing and launching the
APK, so it is intentionally not part of the host regression test.

For repeatable graphics sampling of an already installed build, explicitly
confirm the selected target is a non-VR phone and choose a duration:

```bash
ANDROID_SERIAL=<phone-serial> \
PHONE_BENCHMARK_CONFIRM_NON_VR=YES \
./tests/phone-graphics-benchmark.sh 60
```

The benchmark does not build or install. Raw app-scoped Logcat, thermal and
frame-stat output exists only in a private `/tmp` directory and is deleted on
exit. Its report is refused inside the Git worktree and contains only numeric
aggregates. Native present FPS and p50/p95/max timings come from the latest
complete ten-second window after a successful OpenGL buffer swap; the report
marks Android HWUI frame statistics invalid when they do not cover the native
Qt/OpenGL surface. The same window reports aggregate variable-texture
allocation, populated texture memory, and pending GPU transfers in MiB. Set
`PHONE_BENCHMARK_REPORT` to retain the aggregate summary in a chosen directory
outside the repository.

For a controlled texture-residency A/B run, set
`debug.overte.phone_texture_budget_mb` before starting the process. Values are
bounded to 128–384 MiB and the default remains 256 MiB; 192 MiB is the first
lower-memory candidate to compare. Clear the property after the run. Do not
change the budget while the process is running.

## Release gates

Once both long dependency builds have completed successfully, validate their
existing, complete outputs and publish the content-bound readiness sentinel
without rebuilding:

```bash
./finalize-phone-16k-deps.sh
```

`finalize-phone-16k-deps.sh` is not a recovery build and must not be run to
paper over an interrupted Qt or non-Qt build. It performs no Conan or Gradle
work; missing, stale, changed, or misaligned outputs make it fail without
publishing the sentinel. The non-Qt preparation script normally invokes this
finalizer itself after its build succeeds. Verification also covers the exact
staged OpenSSL files that Gradle copies from `conanlibs/Debug`; replacing or
leaving either staged file stale invalidates the marker even when its Conan
package directory itself is intact.

Between finalizer verification and APK completion, do not run parallel Conan
rebuilds, cache cleans/restores, or manual package changes. The final APK gate
remains authoritative and must pass.

Phone builds fail closed if this sentinel is missing or stale. The explicitly
named `PHONE_ALLOW_LEGACY_4K_DEPS=1` override exists only for temporary local
migration/debugging and must not be used for a distributable APK.

Before publishing, rebuild all Qt/Conan shared libraries with 16 KiB page-size
support. `prepare-phone-16k-conan-deps.sh` invalidates an old readiness marker
before rebuilding and publishes a new marker only after verifying the complete
Qt, OpenSSL, TBB, Node, and WebRTC package set. Gradle enables that dependency
graph only when the marker exists and revalidates it before native compilation.

The 16 KiB Gradle graph also uses modern JNI packaging and automatically runs
the combined ELF and APK-container gate after packaging. Run the same gate on
an existing APK explicitly with:

```bash
./tests/check-phone-apk-16k.sh \
    apps/phoneInterface/build/outputs/apk/release/phoneInterface-release.apk
```

The lower-level ELF check also accepts an unpacked APK or staged library
directory. It is read-only and checks every `.so` and versioned `.so.*` below
that directory. The combined APK gate additionally executes Build-Tools 36
`zipalign -c -P 16 -v 4`.

A production release additionally needs a CI-managed upload key (never stored
in this repository), a monotonically increasing `versionCode`, bundle-size
measurement, SBOM/CVE review of Qt 5, OpenSSL 1.1 and Conan dependencies, and
Play pre-launch testing on both 4 KiB and 16 KiB ARM64 devices.

### Signed Play bundle

Gradle creates an Android App Bundle with `:phoneInterface:bundleRelease`.
Every release invocation requires an explicit positive `VERSION_CODE`; select
a value greater than every version code previously uploaded for
`org.overte.phone`. This local check cannot query Play, so CI or the release
operator remains responsible for monotonicity. The value must also fit
Android's signed 32-bit version-code field (`1` through `2147483647`). The gate
is attached to the release APK and bundle tasks themselves, so it also runs
when they are reached transitively through `build`, publishing, or CI wrapper
tasks. Debug builds default to version code `1` only when `VERSION_CODE` is
entirely absent.

Phone release signing has no default key or password and never falls back to a
keystore from one of the repository's legacy Android clients. If no signing
values are provided, Gradle deliberately produces an unsigned release artifact
suitable for inspection. To create a signed upload bundle, provide all four
values as masked CI environment variables:

```text
OVERTE_ANDROID_KEYSTORE=/secure/path/overte-upload.jks
OVERTE_ANDROID_KEYSTORE_PASSWORD=...
OVERTE_ANDROID_KEY_ALIAS=...
OVERTE_ANDROID_KEY_PASSWORD=...
```

Alternatively, local developers may put those names in their user-level
`~/.gradle/gradle.properties`, which is outside this repository. Never add a
keystore, passwords, a device serial, or a populated signing properties file
to the checkout. A partially configured key fails during Gradle configuration.

After the verified 16 KiB dependencies are ready, create the bundle with:

```bash
./gradlew --settings-file settings-phone.gradle \
    -PVERSION_CODE=<new-positive-integer> \
    -PRELEASE_NUMBER=<version-name> \
    :phoneInterface:bundleRelease
```

Direct `gradlew` invocations do not perform the wrapper's JDK discovery. Set
`JAVA_HOME` to a JDK version from 17 through 21 before running them.

The resulting `.aab` is under
`apps/phoneInterface/build/outputs/bundle/release/`. Enroll the application in
Play App Signing and use the externally managed key above only as its upload
key; the Play-managed app-signing key must not be copied into this repository.
Run the secret-free static release check with:

```bash
./tests/phone-release-config-test.sh
```

## Troubleshooting

### Android dependencies are missing

Populate the source cache with `./build-pico.sh deps --download`, then follow
the complete Qt, non-Qt, and APK sequence under “First setup and required
16 KiB build order”. If the source cache is already populated, start with
`./build-phone-qt-16k.sh`; `./build-phone.sh prepare` alone does not create the
verified 16 KiB dependency outputs.

### No compatible JDK was found

Set `JAVA_HOME` to a JDK from version 17 through 21. The wrapper also checks
common Android Studio and system JDK locations.

### ADB cannot find or authorize the phone

Verify USB debugging, unlock the phone, accept the RSA authorization prompt,
and rerun `adb devices`. Use `ANDROID_SERIAL` if multiple devices are listed.

### The APK exists but does not start

Run the data-minimizing device smoke test against the explicit target. It
restricts logcat to the app process, reduces diagnostics to aggregate results,
and refuses to store reports in the repository:

```bash
ANDROID_SERIAL=<phone-serial> ./tests/phone-device-test.sh
```

Do not capture or commit a global `adb logcat`; it can contain unrelated device,
application, account, and user data. The package name is `org.overte.phone`,
and the launcher activity is `org.overte.phone.PermissionsActivity`.
