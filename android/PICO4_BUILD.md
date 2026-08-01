# Pico 4 dependency preparation and build

The Pico client currently uses a locally built Qt 5 package with two Pico OS
runtime fixes. The fixes are stored as source changes in
`conan/patches/qt-pico-android-runtime.patch`; generated libraries and absolute
links into a Conan cache are intentionally not tracked.

## One-command build

Prerequisites are Conan 2, Android SDK 36 with Platform-Tools, Android NDK
`27.3.13750724`, CMake/Ninja, and a JDK from version 17 through 21. The wrapper
detects the usual Android Studio installation paths; custom locations can be
provided through the environment variables shown by `./build-pico.sh --help`.

For a fresh development environment, install the Conan dependencies, prepare
the runtime files, and build the APK with:

```bash
./build-pico.sh setup
```

The first setup may take a long time because Qt must be built from source.
Later builds detect the existing Conan cache locations, Android SDK, and
Android Studio JDK automatically and can use the faster command:

```bash
./build-pico.sh
```

Individual stages can be run with `./build-pico.sh deps`,
`./build-pico.sh prepare`, and `./build-pico.sh build`. Use
`./build-pico.sh --help` for supported path overrides.

## Install on a Pico 4

Enable developer mode and USB debugging on the headset, connect it over USB,
and accept the authorization prompt inside the headset. Then install an
already built APK with:

```bash
./build-pico.sh install
```

To prepare dependencies, build, and install in one step, use:

```bash
./build-pico.sh deploy
```

The command requires exactly one authorized ADB device. If several devices
are connected, select one with `ANDROID_SERIAL=<serial>`. Existing app data is
preserved because installation uses ADB's replace mode.

## Manual dependency preparation

Install the Pico Conan graph first, including host builds of `glslang`,
`scribe`, `spirv-cross`, and `spirv-tools`. Make those four host executables
available in `PATH`, then provide these package/build locations:

```bash
export PICO_QT_SOURCE_DIR=/path/to/qt/conan/build/qt5
export PICO_QT_BUILD_DIR=/path/to/qt/conan/build_folder
export PICO_TBB_PACKAGE_DIR=/path/to/onetbb/package
export PICO_DRACO_PACKAGE_DIR=/path/to/draco/package

./prepare-pico-deps.sh
```

The Qt source directory must be the `qt5` Git checkout and the build directory
must contain the matching shadow build. The script applies the Pico patch when
needed and automatically rebuilds Qt when it applies the patch. To force
another Qt rebuild, use:

```bash
PICO_REBUILD_QT=1 PICO_BUILD_JOBS="$(nproc)" ./prepare-pico-deps.sh
```

Otherwise, the script stages existing Qt build outputs. It also stages the
release TBB runtime, creates the legacy Draco compatibility layout, and
resolves shader host tools from explicit `PICO_*` variables or `PATH`.

## Build the debug APK

Use the Android Studio JDK (Java 21 in the tested setup), Android SDK 36, and
NDK `27.3.13750724`:

```bash
JAVA_HOME=/path/to/android-studio/jbr \
CMAKE_BUILD_PARALLEL_LEVEL="$(nproc)" \
./gradlew --settings-file settings-pico.gradle \
    :picoInterface:assembleDebug \
    --max-workers="$(nproc)"
```

The APK is written to:

```text
apps/picoInterface/build/outputs/apk/debug/picoInterface-debug.apk
```

`ANDROID_SDK_ROOT` or `ANDROID_HOME` can override the default Android SDK
location. `ANDROID_NDK_HOME` can override the NDK used by the Conan profile.
