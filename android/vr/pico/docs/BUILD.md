# Build the Overte client for Pico 4

> [!CAUTION]
> **AI-assisted experimental Pico 4 port**
>
> This Pico 4 port is developed with the assistance of AI tools. Its code and
> build workflow are experimental and may contain incomplete, poorly tested,
> insecure, or otherwise dangerous changes, including quick-and-dirty fixes.
> Review everything carefully and do not treat this port as production-ready.
>
> This work is maintained separately in a fork in respect of Overte's
> [no-AI-contributions policy](https://github.com/overte-org/overte/blob/master/CONTRIBUTING.md).
> For the official, stable project, use the
> [original Overte repository](https://github.com/overte-org/overte). See the
> fork's [full AI-use disclaimer](../README.md) for more information.

The Pico 4 client has a maintained command-line build workflow for 64-bit
Linux. Run all commands below from the repository's `android/` directory.

## Tested systems

| Operating system | Status |
| --- | --- |
| Fedora Linux 44 | ✅ |
| Ubuntu 24.04 | ✅ |
| openSUSE Tumbleweed | ✅ |
| Arch Linux | ✅ |
| Debian 13 | ✅ |

## Quick start

On a new development machine, install the toolchain and the downloadable Pico
dependencies once:

```bash
cd android
./build-pico.sh bootstrap --with-deps
```

The bootstrap supports Fedora, Debian/Ubuntu, Arch Linux, and openSUSE. It may
request administrator access for missing system packages and Android SDK
license acceptance. When the operating system only provides a newer,
incompatible Java version, the bootstrap installs a checksum-verified Eclipse
Temurin 21 JDK locally. If the base Android command-line tools are missing, the
script displays Google's license page, asks for explicit acceptance, and then
downloads and checksum-verifies the current official Linux tools. Android SDK
Platform 36, Build-Tools 36.0.0, the NDK, and ADB are installed afterward with
`sdkmanager`.

With an authorized Pico 4 connected over USB, build the APK, install it, and
start the client:

```bash
./build-pico.sh deploy
```

Without a connected headset, only build the APK:

```bash
./build-pico.sh
```

To measure the completed client's battery and power use on the headset, see
[Measure Overte power use on Pico 4](PICO4_POWER_TEST.md).

For the device-free pull-request checks and trusted build-runner design, see
[Pico 4 CI/CD](docs/pico4-ci-cd.md).

For world-entry and post-loading optimization measurements, see the
[Pico 4 world-loading guide](docs/world-loading/pico4-optimization-guide.md).

`deploy` assumes that the one-time bootstrap or setup has already installed the
dependencies. It does not download missing Conan packages itself.

## Requirements and automatic setup

The build requires Conan 2, Git, CMake, Ninja, Python, Perl, Android SDK
Platform 36, Build-Tools 36.0.0, NDK `27.3.13750724`, Platform-Tools/ADB,
util-linux `flock`, and a JDK from version 17 through 21. Android Studio is
optional, but provides the Android SDK and a compatible JDK conveniently.

Inspect the complete environment without changing anything:

```bash
./build-pico.sh doctor
```

Missing requirements are reported together with an official installation page
or an appropriate `sdkmanager` command. The automatic bootstrap variants are:

```bash
./build-pico.sh bootstrap
./build-pico.sh bootstrap --check
./build-pico.sh bootstrap --system-packages
./build-pico.sh bootstrap --with-deps
```

- `bootstrap` installs as much of the complete toolchain as possible.
- `--check` is the read-only `doctor` check.
- `--system-packages` only handles packages from the operating system.
- `--with-deps` also installs the downloadable Pico and Conan dependencies.

As an alternative to `bootstrap --with-deps`, an already configured machine can
download dependencies, prepare the runtime, and build the APK in one command:

```bash
./build-pico.sh setup --download
```

The `setup` command runs the environment check before downloading anything.

## Daily development commands

| Command | Purpose |
| --- | --- |
| `./build-pico.sh` | Prepare existing dependencies and build the debug APK |
| `./build-pico.sh build` | Build the debug APK without preparing dependencies again |
| `./build-pico.sh install` | Install and start an already built APK |
| `./build-pico.sh deploy` | Prepare, build, install, and start the client |
| `./build-pico.sh prepare` | Restage existing Conan and runtime dependencies |
| `./build-pico.sh deps --download` | Download and install prebuilt dependencies only |
| `./build-pico.sh --help` | Show commands and supported path overrides |

`PICO_BUILD_JOBS` bounds Gradle, native compilation, and shader generation to
the same host-worker count. `PICO_SHADER_JOBS` can override only shader
generation when memory or shared-runner load requires a lower limit. Use
`./build-pico.sh build --stacktrace` to include Gradle failure details when
diagnosing an unsuccessful CI or local build.

Before building, or on a host without Pico/Android dependencies, run the
device-free regression suite from the repository root:

```bash
./android/vr/pico/tests/pico-device-free-test.sh
```

It performs shell syntax checks and the WebView, microphone, OpenXR lifecycle,
runner-mock, serverless-fixture, device-lock, and power-analyzer regressions. It
does not invoke ADB, connect to a device, download dependencies, or modify
device settings. Native Qt/C++ suites remain available separately through
`android/vr/pico/tests/pico-host-regression-test.sh` when a CMake build is configured.

After a build, verify that the output is a signed, structurally valid Pico APK:

```bash
./ci/verify-pico-apk.py \
  vr/pico/apps/picoInterface/build/outputs/apk/debug/picoInterface-debug.apk \
  --output ../build/pico4/apk-manifest.json
```

The verifier fails closed if the package identity, SDK levels, signature,
ARM64-only ABI set, ZIP integrity, or required Pico/OpenXR native libraries do
not match the application contract. It writes the version, size, and SHA-256
digest to a small JSON manifest suitable for CI retention. `aapt` and
`apksigner` must be on `PATH`, or their exact Build-Tools paths can be provided
with `--aapt` and `--apksigner`.

## Default Pico graphics profile

The Pico Interface uses the measured Pico 4 quality/performance baseline by
default: 80% OpenXR render scale at the runtime's lowest supported refresh rate
(72 Hz on Pico 4), forward rendering, low world detail, and no shadows, bloom,
ambient occlusion, antialiasing, fixed foveation, or statistics overlay. Haze,
local lights, and procedural materials remain enabled because disabling them
did not produce a repeatable benefit.

The render scale can be changed under **Settings > Graphics > Pico render
resolution** and takes effect after the prompted app restart. See
[Pico 4 graphics optimization results](docs/power-tests/pico-graphics-optimization.md)
for the controlled measurements and rejected alternatives.

Restart arguments are stored once in app-private preferences before the old
process exits. The exported launcher cannot accept raw command arguments from
another application, and the internal Qt Activity is not exported.

## Sharing one headset between worktrees

All tracked Pico device runners coordinate through an exclusive lock in the
repository's Git common directory. Linked worktrees share that directory, so a
test in one Codex session makes another session wait before its first ADB
operation instead of changing the app, fan, properties, or scene underneath
the active test.

Check the shared state or wrap an ad-hoc device command explicitly:

```bash
./pico-device-lock.sh status
./pico-device-lock.sh run -- "${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}/platform-tools/adb" devices
```

`status` exits with 1 while the headset is occupied and reports only the holder
PID, start time, and branch. `run` prints that it is waiting, blocks until the
current operation releases the lock, and releases it when its command exits or
is interrupted. Use the wrapper for every manual ADB sequence. The Pico build
installer, power runner, graphics/avatar matrices, simpleperf, unattended
controller, and microphone runner acquire it automatically.

The coordination behavior can be tested without ADB or a headset:

```bash
./tests/pico-device-lock-test.sh
```

## Prebuilt dependencies

The recommended download path restores checksum-verified Conan cache packages
for Qt 5.15.18 and Node.js 22.22.3 together with the patched Qt/TBB runtime.
The three archives total approximately 1.1 GiB. Smaller dependencies are then
resolved normally through Conan. The script automatically configures Overte's
public official Conan repository for Overte-specific packages.

The files are published in the
[Pico 4 prebuilt dependencies v1 release](https://github.com/noah-be/overte/releases/tag/pico4-deps-v1).
Their SHA-256 checksums are versioned in
`conan/prebuilt/pico4-deps-v1.sha256` and verified before extraction.

The staged runtime fixes originate from
`conan/patches/qt-pico-android-runtime.patch`. Generated runtime libraries and
absolute links into a developer's Conan cache are intentionally not tracked by
Git.

## Install and run on a Pico 4

Enable developer mode and USB debugging on the headset, connect it over USB,
and accept the authorization prompt inside the headset. Verify the connection
when necessary:

```bash
"${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}/platform-tools/adb" devices
```

The device must appear with the state `device`. If it shows `unauthorized`, put
on the headset and accept the USB debugging prompt before retrying.

Use `./build-pico.sh deploy` to build a new APK before installation, or
`./build-pico.sh install` to reinstall the existing APK without rebuilding it.
Both installation paths preserve existing app data, start the launcher
activity automatically, and verify that the app process remains active.

For reproducible Pico microphone source and fan-noise tests, see
[`docs/pico-microphone.md`](docs/pico-microphone.md). The accompanying
`pico-microphone-test.sh` script restores automatic fan control and stops the
app after each run.

For controller-to-entity debugging, see the
[object interaction architecture and hardware test matrix](docs/pico4-object-interaction.md).

The command expects exactly one authorized ADB device. Select a device
explicitly when several are connected:

```bash
ANDROID_SERIAL=<serial> ./build-pico.sh deploy
```

## Build output

The wrapper builds the `picoInterface` debug variant. The APK is written to:

```text
vr/pico/apps/picoInterface/build/outputs/apk/debug/picoInterface-debug.apk
```

## Troubleshooting

Start with the environment report:

```bash
./build-pico.sh doctor
```

Common issues are:

- Android command-line tools are installed, but SDK Platform 36, Build-Tools
  36.0.0, the exact NDK, or Platform-Tools are missing. Follow the printed
  `sdkmanager` command or rerun `./build-pico.sh bootstrap`.
- Conan was installed but has no default profile. The bootstrap creates it, or
  it can be created manually with `conan profile detect --force`.
- A connected Pico is `unauthorized`. Accept the prompt inside the headset and
  check the device list with the Platform-Tools command shown above.
- Several ADB devices are connected. Set `ANDROID_SERIAL` as shown above.
- Custom installations are not detected. Use `ANDROID_SDK_ROOT`,
  `ANDROID_NDK_HOME`, `JAVA_HOME`, or the `PICO_*` overrides listed by
  `./build-pico.sh --help`.

## Advanced: source builds and dependency maintenance

Downloading the published Qt and Node artifacts is the normal path. To build
all missing dependencies locally from source instead, omit `--download`:

```bash
./build-pico.sh setup
```

The first source build can take several hours. Qt 5's bundled Mapbox/Boost code
requires the compatibility flags pinned in `conan/profiles/pico4-arm64`, and
the Pico runtime patch is applied before the required Qt runtime libraries are
staged.

For manual dependency maintenance, install the Pico Conan graph and its host
builds of `glslang`, `scribe`, `spirv-cross`, and `spirv-tools`. Make those host
executables available in `PATH`, then provide the package and build locations:

```bash
export PICO_QT_SOURCE_DIR=/path/to/qt/conan/build/qt5
export PICO_QT_BUILD_DIR=/path/to/qt/conan/build_folder
export PICO_TBB_PACKAGE_DIR=/path/to/onetbb/package
export PICO_DRACO_PACKAGE_DIR=/path/to/draco/package

./prepare-pico-deps.sh
```

The Qt source directory must be the `qt5` checkout corresponding to the shadow
build. The preparation script applies the Pico runtime patch when needed and
rebuilds QtBase after applying it. Force another QtBase rebuild with:

```bash
PICO_REBUILD_QT=1 PICO_BUILD_JOBS="$(nproc)" ./prepare-pico-deps.sh
```

The script also stages the release TBB runtime, creates the legacy Draco
compatibility layout, and resolves shader host tools from explicit `PICO_*`
variables or `PATH`.
