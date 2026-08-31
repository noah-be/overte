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

For the device-free Actions checks and trusted build-runner architecture, see
[Android Phone CI/CD](ANDROID_PHONE_CI_CD.md).

Run the commands in this document from the repository's `android/` directory.

## Fast x86_64 emulator tests

The production Phone APK remains ARM64-only. For local instrumentation tests,
the separate `emulator` build type compiles the complete application and its
native dependency graph for x86_64 so a matching AVD can use KVM acceleration.
It cannot be selected accidentally by the normal debug or release commands.

The local default is the `overte_api35` AVD. Select another existing x86_64
AVD with `PHONE_EMULATOR_AVD=<name>`. Check the host without starting it:

```bash
./phone-emulator-test.sh doctor
```

Build the x86_64 dependencies and app, boot the headless emulator, disable
system animations, and run the AndroidX instrumentation suite:

```bash
./phone-emulator-test.sh all
```

The included smoke test runs inside Android and verifies that the installed
Phone package is executing on an x86_64 device and contains the native
`libphoneInterface.so` for that ABI. Add further device tests below
`phone/apps/phoneInterface/src/androidTest/`.

The first dependency build compiles Qt and the other Android native packages
and is substantially slower than later incremental runs. Individual phases
are available as `deps`, `build`, `start`, `test`, and `stop`. The runner only
stops an AVD when explicitly invoked with `stop`.

See [EMULATOR_TESTS.md](EMULATOR_TESTS.md) for the
implementation details, validated baseline, limitations, and test roadmap.

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

The final APK content gate also requires every explicitly staged startup,
network, image, audio, positioning, and QML plugin runtime. The QML/plugin set
is read from `qt_dependencies.xml`, so adding a loader declaration cannot drift
away from the archive gate. Every declared QML module must also retain its
`qmldir` metadata in the archive. This catches incomplete incremental packages
before an APK can fail later at launch or first use.

The generated `cache_assets.txt` extraction manifest is also treated as an
untrusted package boundary: timestamps must be bounded ASCII integers, asset
paths must be unique and relative, and Java canonicalizes every destination
below the application cache before writing it.

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

The doctor command uses the established shared environment checker because both
applications intentionally use the same toolchain versions. Its Phone wrapper
prints the Phone-specific 16-KiB setup hand-off rather than Pico build steps.
It separately reports `[SETUP]` or `[READY]` for the atomic Phone dependency
marker, so a complete host toolchain is not confused with a build-ready graph.
When the marker exists, doctor runs the complete read-only content, symlink,
and ELF-alignment verifier before reporting `[READY]`; mismatch reports
`[STALE]` and fails. Gradle revalidates the same contract before compiling.
Doctor intentionally reduces stale details to that aggregate status so shared
logs do not expose host package paths; run the verifier directly for local
path-specific diagnosis.

## First setup and required 16 KiB build order

The phone build uses the same pinned dependency sources and recipes as the
Pico build, but its native libraries must be rebuilt into dedicated 16 KiB
outputs. Run these phases in order:

The two long dependency helpers require at least 32 GB (decimal) of configured
swap before they change build outputs. They always use four build jobs and
restart themselves in a transient systemd user service with
`MemoryMax=16000000000`
(exactly 16 GB decimal). The active
cgroup limit is verified after restart. A host without transient systemd user
services, a
smaller swap allocation, or an unverifiable memory limit therefore stops
before the dependency build; there is intentionally no unbounded fallback.

1. On a normal development machine, restore both the shared Pico/Phone cache
   and the smaller Phone-specific 16 KiB delta, then build:

   ```bash
   ./build-phone.sh setup --download
   ```

   Both archives are SHA-256 verified before Conan sees them. The Phone delta
   is restored with `--build=never`, regenerated into the two dedicated output
   directories, and accepted only if the complete content-bound 16 KiB marker
   can be finalized. A missing artifact, checksum mismatch, missing package, or
   failed ELF inspection stops closed. Restoring the shared Pico artifacts does
   not resolve or compile their source graph in this workflow; in particular,
   it must not trigger a local Node/V8 build.

   The large download is staged under `android/build/prebuilt-tmp` rather than
   the system temporary directory, avoiding small or memory-backed `/tmp`
   limits on CI runners. `PHONE_PREBUILT_TMPDIR` can select another large local
   filesystem; temporary content is removed on success and failure. Dependency
   verification similarly uses `android/build/verification-tmp` and can be
   redirected with `PHONE_VERIFY_TMPDIR`.

   `PHONE_SHARED_CONAN_HOME` selects the cache used only for shared Pico runtime
   and host tools. Keep `CONAN_HOME` separate for the verified Phone dependency
   graph; the trusted workflow does this automatically.

   Gradle/APK packaging uses `android/build/package-tmp` instead of a potentially
   memory-backed system `/tmp`; override it with `PHONE_BUILD_TMPDIR` if needed.
   The Phone entry point assigns Gradle a 6 GB heap so packaging the large
   native debug libraries does not exhaust the default JVM heap. Override it
   with `PHONE_GRADLE_JVM_ARGS` on hosts with different memory limits.

   To restore only the dependency graph without preparing or building the APK,
   use the Phone entry point just as with Pico:

   ```bash
   ./build-phone.sh deps --download
   ```

   This command downloads only the complete pinned Phone Conan graph from
   [`android-phone-16k-deps-v3`](https://github.com/noah-be/overte/releases/tag/android-phone-16k-deps-v3).
   Phone dependency transport is independent from
   Pico release assets and cannot silently enter Pico's `--build=missing`
   producer phase.

The remaining steps are the one-time artifact-producer path. They are not
needed after the current Phone delta has been published:

2. Artifact maintainers can build the complete dependency graph locally with
   the matching Phone command. This is the slow producer fallback and is not
   part of normal developer setup:

   ```bash
   ./build-phone.sh deps
   ```

   It installs the shared Android graph, rebuilds Qt for 16 KiB pages, rebuilds
   the non-Qt Phone dependencies, and finalizes the verified sentinel. The
   equivalent explicit producer phases are shown below for diagnosis only.

3. Explicitly rebuild Qt for 16 KiB pages. This is the longest dependency
   phase:

   ```bash
   ./build-phone-qt-16k.sh
   ```

4. Rebuild the non-Qt dependencies. The script verifies the complete Qt and
   non-Qt graph and publishes the content-bound readiness marker only after
   successful verification:

   ```bash
   ./prepare-phone-16k-conan-deps.sh
   ```

5. Export the exact source-free 16 KiB dependency graph to a release-ready archive and
   checksum manifest (the destination must be absolute):

   ```bash
   ./phone-prebuilt-16k-deps.sh export /absolute/output/directory
   ```

   Publish the generated `android-phone-16k-conan.tgz` under the
   `android-phone-16k-deps-v3` release tag, then review and commit the generated
   `android-phone-16k-deps-v3.sha256`.

6. Build the APK from the verified graph:

   ```bash
   ./build-phone.sh build
   ```

The prebuilt archive contains the exact pinned Phone target and build-context
binary graph and no sources. The offline installs and final verifier prove that
the archive is complete and 16 KiB compatible. Regenerate it whenever a recipe
revision, profile, NDK, option, dependency, or pinned build profile changes. Normal
`build`, `install`, and `deploy` commands can be used once the dedicated
outputs and readiness marker exist.

## Development commands

| Command | Purpose |
| --- | --- |
| `./build-phone.sh doctor` | Inspect the shared Android build environment |
| `./build-phone.sh deps --download` | Restore all published shared and Phone-specific dependencies without source builds |
| `./build-phone.sh deps` | Slow artifact-producer fallback: build and verify missing dependencies locally |
| `./build-phone.sh prepare` | Restage already available Qt/Conan dependencies |
| `./build-phone.sh build` | Build the debug APK from verified 16 KiB dependencies |
| `./build-phone.sh` | Prepare dependencies and build the debug APK |
| `./build-phone.sh install` | Install and start an already built APK |
| `./build-phone.sh deploy` | Prepare, build, install, and start the app |
| `./build-phone.sh setup --download` | Restore shared plus Phone 16 KiB artifacts, verify, and build |
| `./phone-prebuilt-16k-deps.sh export /absolute/path` | Produce the release-ready Phone cache delta and checksum |
| `./build-phone.sh --help` | Show the command summary |

Limit native compilation parallelism performed through `build-phone.sh` when
memory is constrained:

```bash
PHONE_BUILD_JOBS=4 ./build-phone.sh
```

This setting is forwarded to the wrapper's prepare and CMake build phases. It
also bounds Gradle, Ninja, and shader generation; native linking remains
serial to avoid memory spikes. It does not override the fixed four-job count in
the dedicated Conan 16 KiB profiles. The long dependency helpers additionally enforce their documented
32 GB swap prerequisite and 16 GB decimal cgroup memory ceiling.

Use `./build-phone.sh build --stacktrace` to include Gradle failure details in
CI or local build diagnostics.

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
phone/apps/phoneInterface/build/outputs/apk/debug/phoneInterface-debug.apk
```

## Static regression check

Run the complete device-free gate before handing off a Phone branch. It uses
source checks, unit/contract fixtures, JavaScript syntax, Java compilation, and
mock ADB only; it never invokes the real device or graphics benchmark runners:

```bash
./tests/phone-static-regression-test.sh
```

The mock graphics-benchmark harness deliberately exercises real timeout
windows, so the complete gate takes longer than the focused checks. Run the
lightweight module check after changing only the manifest, wrapper, or module:

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

Phone preparation validates that the shared Draco compatibility archive is an
Android `armv8` Conan package containing AArch64 objects before staging it. This
prevents a newer host-side Conan package from being selected merely because its
cache timestamp is newer. The package gate separately maintains an exact
allowlist for linked native modules because Qt's `bundled_in_lib` resource lists
runtime-tree plugins, not the normal ELF dependency graph.

At startup, `PermissionsActivity` handles the optional microphone permission
and transfers control to `PhoneInterfaceActivity`. The latter hosts the native
Qt client, unpacks its assets into the application cache, and keeps the display
awake while the client is active. Hidden and suspended Qt application states
are treated as background states; transient Back-key and pending URL retry
bookkeeping is stopped or reset on Activity pause and resumed safely later.
Android cloud backup and device-to-device transfer are both denied across all
credential- and device-protected app-data domains so account state and cached
world data cannot silently migrate through platform backup. The structured
data-protection gate also permits exactly the five required Android permissions
and two Activities, with only the launcher exported; new aliases, providers,
receivers, services, or entry points fail closed pending explicit review.

### Touchscreen system tablet

The Android client reuses Overte's established `TabletScriptingInterface`,
`TabletProxy`, and Tablet QML application API. It does not start the VR-only
`WebTablet` entity, hand, laser, or HMD presentation. The mobile action bar
presents the existing tablet window as a full-screen screen-space surface and
resizes it with the Android viewport.

While the tablet is visible, the virtual pad and mobile action/audio bars are
hidden so world controls cannot receive touch-through input. Android Back first
closes the phone login or address dialog, then returns a tablet application to
the tablet Home screen, and finally closes the tablet. Desktop and VR tablet
presentation remain unchanged.

`TabletHome.qml` uses a selector-backed presentation configuration. Android
uses a touch-oriented responsive grid with five columns in landscape, three in
portrait-sized lifecycle transitions, and 48-pixel page targets. The shared
Tablet button model and `Tablet.addButton()` compatibility remain intact.

Application support is intentionally explicit rather than inferred from an
app having a tablet button:

| Surface | Device-free status | Remaining device validation |
| --- | --- | --- |
| Login | Screen-space QML, native IME fields, touch-sized entry, cancellable pending request, idempotent focus cleanup | IME resize and real account/domain authentication |
| Settings | Local QML with selector-backed 250% host scaling; General Settings is fail-closed to Phone Navigation and touch-look sensitivity; Security allowlists are normalized and IME-safe; incomplete scripting-plugin, controller, VR, and unbounded desktop Graphics controls are neither shown nor constructed | Every retained subpage and allowlist editor |
| Audio | Local QML locked to the available non-HMD context; redundant mode tab, keyboard PTT, HMD, and desktop avatar-audio overlays are selector-gated out | Device enumeration, sliders, mute, stereo and scrolling |
| Menu | Local QML navigation | Each retained action and modal result |
| Shield | Native privacy-radius action; closes the phone tablet after activation | Visible/audio feedback and repeated activation |
| People | Local QML application | Live presence, touch selection and domain changes |
| Emote | Local touch QML with validated animation allowlist and lifecycle-owned playback | Animation loading, all actions, repeated stop/switch, movement interruption and avatar restoration |
| Avatar | Local QML bookmarks/settings; external marketplace web pages are explicitly unavailable | Bookmark changes, wearable editing and failure feedback |
| Places | Local `PicoPlaces.qml`; guarded QML lifecycle and bounded navigation messages without destination logging | Network failure, federation data and destination loading |
| Tutorial | Bundled serverless destination; closes the tablet before navigation | Loading and return behavior |
| Home | Configured home bookmark with bundled Tutorial fallback | Valid, invalid and unreachable bookmark behavior |
| Create | Disabled | Requires a dedicated touch design without desktop windows, controller mappings or entity-click capture |

One Create prerequisite is now available independently of its UI: Android can
use the QuaZip package already present in the shared Conan graph for ZIP-backed
model imports. Before extraction, the client rejects absolute, non-canonical,
duplicate, overlong, and symbolic-link entries and enforces per-file,
total-expanded-size, and entry-count limits. Validation and extraction share a
single read-only file handle. This does not enable Create or its desktop UI.

Users, More, VR tablet positioning, and other remote-web/VR-only tablet scripts
remain disabled until they have an equally explicit phone contract. The legacy
Web/controller Emote script also remains disabled; Phone uses its dedicated
native-QML implementation instead.

### Tablet device-validation status

A focused phone spot check on 2026-08-08 confirmed that the tablet launcher and
the currently enabled applications open, and that the Audio and Avatar views
render after the incremental QML resource-regeneration fix. This is an
integration observation, not release coverage. The following checks remain
required before the tablet application set and login workflow can be treated as
fully validated:

- Login success, invalid credentials, cancellation, Android Back, IME resize,
  and focus release against a real account and online domain.
- Audio device enumeration, microphone mute, push-to-talk, every slider,
  scrolling, and repeated open/Back/reopen behavior with active audio.
- Avatar list/header spacing at supported phone sizes, hidden phone-only HMD
  and dominant-hand controls, Save/Cancel placement and behavior, bookmarks,
  wearables, malformed content, and failure feedback.
- Places directory loading, refresh, slow/offline/error responses, federation
  selection, long-list scrolling, and navigation to multiple real online
  destinations.
- People presence and selection with multiple live avatars, audio levels,
  domain changes, server-backed actions, and teardown after Back or disconnect.
- Menu action coverage, including confirmation that the legacy General Settings
  dialog stays unavailable while the dedicated tablet Settings app remains
  usable.
- Cross-app lifecycle coverage: repeated open, Android Back to tablet Home,
  close, background/foreground, reconnect, IME teardown, and restoration of
  world and mobile controls.
- Broader hardware coverage on at least one Adreno and one Mali phone, including
  unusual DPI/cutout layouts and sustained performance.

Do not interpret a successful launch, one visual pass, or the static contract
suite as completing any of these runtime checks. Record only aggregate,
non-identifying results; keep screenshots and raw logs private and temporary.

Run the device-free tablet contract checks with:

```bash
./tests/phone-tablet-static-test.sh
```

This aggregate gate runs every app contract, JavaScript syntax checks, the
complete phone host regression suite, and `git diff --check`. Create remains
disabled until `phone-tablet-create-contract-test.sh` can be replaced by tests
for touch-owned entity selection, screen-space dialogs, camera/render state
restoration, and repeated open/Back/reopen lifecycle behavior.

## Device validation checklist

A successful build is only the first gate. Before calling a change usable,
exercise it on at least one Adreno and one Mali device and record:

1. fresh install, launch, microphone accept and deny paths;
2. connection to a domain and visible 2D scene rendering;
3. movement, camera look, jump/action controls, and multi-touch;
4. audio input/output, Android keyboard, and login/navigation UI;
   for tablet changes, also verify Tablet open/close, Audio and Settings,
   app-to-Home-to-close Back navigation, page swipes, and no world-control
   touch-through;
5. background/foreground transitions, screen rotation policy, and reconnects;
6. memory use, frame pacing, temperature, and battery drain over a long run.

For a shared development phone, run the complete build/install/test capture in
one invocation of the external phone-device-lock wrapper. Check its `status`
first, wait when occupied, and pass a single `run -- bash -c '...'` transaction
that contains the incremental build, 16 KiB APK gate, device selection,
installation, launch, diagnostics, and test. Inside that transaction:

- derive `ANDROID_SERIAL` silently from `adb devices -l`;
- require exactly one authorized non-VR phone and reject Pico/Bytedance devices;
- use `adb -s "$ANDROID_SERIAL"` for every command;
- never uninstall or clear application data;
- keep screenshots and raw logs under a temporary private directory;
- retain only aggregate, non-identifying results after releasing the lock.

The prepared manual sequence is: open Tablet; exercise Login cancel/failure/
success and Back with the IME visible; open and Back/reopen Settings, Audio,
Menu, People, Avatar, and Places; activate Shield; navigate through Tutorial
and configured/unconfigured Home; confirm Create is absent; then verify that
closing every surface restores world controls and focus. Do not start this
sequence until the phone owner explicitly releases the device for testing.

Cutouts, gesture navigation, unusual DPI values, and vendor-specific power
management deserve explicit checks. Automated static validation cannot expose
these device/runtime problems.

Run the repeatable smoke test against an already built APK with an explicit
device serial. It first uses SDK `apkanalyzer` to require the dedicated Phone
application ID, API 26/36 SDK contract, and exact five-permission allowlist.
It also runs the full contents, ELF, 16-KiB alignment, and padding gate. It then
selects and queries the target phone, installs the app, verifies the installed
bytes, and exercises launch, a fixed local test deep link, three
background/foreground cycles, and a
process-preserving Back/background/recovery cycle. It records aggregate crash
and 16 KiB compatibility diagnostics in a temporary report directory:

The gate executable can be replaced only by the device-free mock harness with
the explicit `PHONE_ALLOW_TEST_OVERRIDES=1`; real runs use the repository gate.

```bash
ANDROID_SERIAL=<phone-serial> ./tests/phone-device-test.sh
```

Pass an APK path as the optional first argument. `PHONE_TEST_REPORT` may point
to an existing directory outside the Git worktree when reports should be
retained at a known location. That directory must not already contain
`summary.txt`; the test refuses to overwrite files or follow a summary symlink.
Device diagnostics are refused inside the repository, and the summary is
created with owner-only permissions. It contains only the app package,
lifecycle status flags,
and aggregate test counts: it never records the device serial, model, deep-link
URI, account data, process IDs, or raw Android output. Console output likewise
identifies the report only as
temporary or caller-provided; it never prints its absolute path. Set
`PHONE_TEST_REPORT` when a known retained location is required.
Raw ADB stderr is reduced to generic phase errors so serials and host paths do
not enter captured output.
Set `PHONE_EXPECT_DEBUGGABLE=0` for a release smoke or `1` for a debug smoke;
the validated state is recorded as a boolean in the summary.
Always require the final `test_status=passed`; earlier lifecycle fields are
incremental evidence and a failed run records `test_status=failed` on exit.
Successful runs also require `cleanup_force_stopped=1`. The APK and its data
remain installed, but the app is not left foregrounded or keeping the display
awake; post-install failures attempt the same cleanup before returning.
Logcat is restricted to the tested app process and inspected only as a stream;
an on-device epoch cursor also excludes entries older than this test launch.
Package exit diagnostics
are likewise reduced immediately to a count. Neither raw source is written to
the report.
The script never uses ADB's implicit default device: without
`ANDROID_SERIAL`, it proceeds only if exactly one authorized physical ARM64
touchscreen phone meeting API 26 and OpenGL ES 3.2 requirements is
identifiable. It exits with status 2 when crash or page-size-mismatch log lines
are detected. The test changes device state by installing and launching the
APK, so it is intentionally not part of the host regression test.

For repeatable graphics sampling of an already installed current build,
explicitly confirm the selected target and choose a duration:

```bash
ANDROID_SERIAL=<phone-serial> \
PHONE_BENCHMARK_CONFIRM_NON_VR=YES \
./tests/phone-graphics-benchmark.sh 60
```

The benchmark does not build or install. It accepts only the explicitly named,
authorized physical non-Pico ARM64 touchscreen Phone meeting API 26 and OpenGL
ES 3.2 requirements; emulator, Watch, TV, Automotive and VR targets fail before
the app is touched. Duration is bounded to 1–3600 seconds and
`PHONE_BENCHMARK_INTERVAL` to 1–300 seconds.

For repeated online-world loading measurements, including CPU, memory,
per-UID network traffic, frame jank, thermals, battery and optional Perfetto
traces, use `tests/phone-world-loading-test.sh`. The complete invocation and
interpretation guide is in
[`ANDROID_PHONE_PERFORMANCE_TESTING.md`](ANDROID_PHONE_PERFORMANCE_TESTING.md).

Raw app-scoped Logcat, thermal and frame-stat output exists only in a private
`/tmp` directory and is deleted on exit. INT, TERM, successful collection and
every late failure force-stop an app that the harness started. A successful
summary is published only after the required final stop succeeds and contains
`cleanup_force_stopped=1`; cleanup failure leaves no successful summary.

The aggregate report is refused inside the Git worktree and contains only
validated numeric aggregates. Native present FPS and p50/p95/max timings come
from the latest complete ten-second window after a successful OpenGL buffer
swap; the report
marks Android HWUI frame statistics invalid when they do not cover the native
Qt/OpenGL surface. The same window reports aggregate GPU buffer and texture
memory, deferred GL cleanup, process/allocator memory, framebuffer recreation,
pending GPU transfers, and the latest GPU-frame and batch timings already
maintained by the render context. The latest complete overlay-cache sample adds
its validated hit ratio; missing or inconsistent counters are reported as
unknown. Set `PHONE_BENCHMARK_REPORT` to atomically replace `summary.txt` in a
chosen private directory outside the repository without printing that caller
path. If it is unset, the harness prints the generated non-personal
`/tmp/overte-phone-graphics-report.*/summary.txt` path; that aggregate directory
persists until the caller removes it.

The process-start Android properties below support controlled A/B runs:

- `debug.overte.phone_render_scale`: 0.50–0.70, default 0.65;
- `debug.overte.phone_texture_budget_mb`: 128–384 MiB, default 256 MiB;
- `debug.overte.phone_overlay_scale`: 0.50–1.00, default 1.00;
- `debug.overte.phone_overlay_depth`: recognized true values restore the
  legacy overlay depth attachment; default and invalid values keep it off;
- `debug.overte.phone_overlay_cache`: default on; recognized false values and
  invalid values disable it as a safe fallback;
- `debug.overte.phone_haze` and `debug.overte.phone_local_lights`: default off
  experimental quality switches.

Use 192 MiB as the first lower texture-residency candidate and 0.75 as the
first lower overlay-scale candidate. Change only one property per comparison,
force-stop and restart the process, keep the scene and warm-up duration fixed,
and clear the property afterwards. Do not change these properties while the
process is running. Never put a real device serial or raw benchmark output in
the repository.

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

The 16 KiB Gradle graph keeps the JNI libraries extracted as required by the
Qt 5 Android loader and automatically runs the combined ELF and APK-container
gate after packaging. Run the same gate on an existing APK explicitly with:

```bash
./tests/check-phone-apk-16k.sh \
    phone/apps/phoneInterface/build/outputs/apk/release/phoneInterface-release.apk
```

The lower-level ELF check also accepts an unpacked APK or staged library
directory. It is read-only and checks every `.so` and versioned `.so.*` below
that directory. The combined APK gate additionally executes Build-Tools 36
`zipalign -c -P 16 -v 4` and rejects excessive padding between ZIP entries.
If the padding check fails after packaged inputs shrink, delete only the
generated APK output and rerun the same Gradle packaging task; do not clean the
native build tree. Deleting the output from inside Gradle's package task is not
safe because its incremental plan has already been selected. The contents gate
also rejects partial APKs and verifies every entry named by `cache_assets.txt`.
The combined gate uses SDK `apkanalyzer` on the merged binary manifest to
require the Phone package ID, API 26/36 bounds, exact five-permission allowlist,
bounded version code/name, and a valid boolean debuggable state before
inspecting native/container data. Free-form version names are validated but
never echoed by the gate.
Gradle additionally requires `true` for debug APKs and `false` for release APKs.

A production release additionally needs a CI-managed upload key (never stored
in this repository), a monotonically increasing `versionCode`, bundle-size
measurement, SBOM/CVE review of Qt 5, OpenSSL 1.1 and Conan dependencies, and
Play pre-launch testing on both 4 KiB and 16 KiB ARM64 devices.

### Signed Play bundle

Gradle creates an Android App Bundle with `:phoneInterface:bundleRelease`.
Every release invocation requires an explicit positive `VERSION_CODE` and an
explicit `RELEASE_NUMBER`; select a code greater than every code previously uploaded for
`org.overte.phone`. This local check cannot query Play, so CI or the release
operator remains responsible for monotonicity. The value must also fit
Android's signed 32-bit version-code field (`1` through `2147483647`). The gate
is attached to the release APK and bundle tasks themselves, so it also runs
when they are reached transitively through `build`, publishing, or CI wrapper
tasks. Debug builds default to version code `1` only when `VERSION_CODE` is
entirely absent.

`RELEASE_NUMBER` becomes Android's `versionName` and must contain 1–100
portable characters: letters, digits, `.`, `_`, `+`, or `-`, beginning with a
letter or digit. This prevents an inspection default or unsafe branch text from
silently becoming public release metadata.

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
`phone/apps/phoneInterface/build/outputs/bundle/release/`. Enroll the application in
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
