# Build the Overte client for Pico 4

The Pico 4 client has a maintained command-line build workflow for 64-bit
Linux. Run all commands below from the repository's `android/` directory.

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
Temurin 21 JDK locally. If the base Android command-line tools are not
installed, the script prints Google's official download page. Install those
tools, then run the bootstrap command again.

With an authorized Pico 4 connected over USB, build the APK, install it, and
start the client:

```bash
./build-pico.sh deploy
```

Without a connected headset, only build the APK:

```bash
./build-pico.sh
```

`deploy` assumes that the one-time bootstrap or setup has already installed the
dependencies. It does not download missing Conan packages itself.

## Requirements and automatic setup

The build requires Conan 2, Git, CMake, Ninja, Python, Perl, Android SDK
Platform 36, Build-Tools 36.0.0, NDK `27.3.13750724`, Platform-Tools/ADB, and a
JDK from version 17 through 21. Android Studio is optional, but provides the
Android SDK and a compatible JDK conveniently.

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

## Prebuilt dependencies

The recommended download path restores checksum-verified Conan cache packages
for Qt 5.15.18 and Node.js 22.22.3 together with the patched Qt/TBB runtime.
The three archives total approximately 1.1 GiB. Smaller dependencies are then
resolved normally through Conan.

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

The command expects exactly one authorized ADB device. Select a device
explicitly when several are connected:

```bash
ANDROID_SERIAL=<serial> ./build-pico.sh deploy
```

## Build output

The wrapper builds the `picoInterface` debug variant. The APK is written to:

```text
apps/picoInterface/build/outputs/apk/debug/picoInterface-debug.apk
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
