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
> The shared Pico Qt/Conan runtime is currently built with 4 KiB ELF segment
> alignment. Although the phone target enables flexible 16 KiB page sizes for
> newly linked code, the resulting package is **not ready for Google Play or
> 16 KiB-only devices** until every bundled native dependency has been rebuilt
> and verified with 16 KiB alignment.

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

## First setup

If this checkout already has the Pico Qt and Conan dependencies, prepare them
and build the phone APK with:

```bash
./build-phone.sh
```

On a new development machine, explicitly allow the dependency download:

```bash
./build-phone.sh setup --download
```

The download is large and is never performed by `doctor`, `build`, or the
static regression test. The phone build reuses the existing Pico dependency
archives and runtime compatibility libraries; this avoids maintaining a
second, subtly different Qt-for-Android stack while the phone port matures.

## Development commands

| Command | Purpose |
| --- | --- |
| `./build-phone.sh doctor` | Inspect the shared Android build environment |
| `./build-phone.sh prepare` | Restage already available Qt/Conan dependencies |
| `./build-phone.sh build` | Build the debug APK without preparing again |
| `./build-phone.sh` | Prepare dependencies and build the debug APK |
| `./build-phone.sh install` | Install and start an already built APK |
| `./build-phone.sh deploy` | Prepare, build, install, and start the app |
| `./build-phone.sh setup --download` | Download dependencies, prepare, and build |
| `./build-phone.sh --help` | Show the command summary |

Limit native compilation parallelism when memory is constrained:

```bash
PHONE_BUILD_JOBS=4 ./build-phone.sh
```

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

When more than one Android device is connected, select one explicitly:

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

## Release gates

Before publishing, rebuild all Qt/Conan shared libraries with 16 KiB page-size
support and reject any packaged ELF whose `LOAD` alignment is below `0x4000`.
Also validate the APK container alignment with Build-Tools 36:

```bash
./tests/check-phone-elf-alignment.sh \
    apps/phoneInterface/build/outputs/apk/release/phoneInterface-release.apk
"${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}/build-tools/36.0.0/zipalign" \
    -c -P 16 -v 4 phoneInterface-release.apk
```

The ELF check also accepts an unpacked APK or staged library directory. It is
read-only and checks every `.so` below that directory.

A production release additionally needs a CI-managed upload key (never stored
in this repository), a monotonically increasing `versionCode`, bundle-size
measurement, SBOM/CVE review of Qt 5, OpenSSL 1.1 and Conan dependencies, and
Play pre-launch testing on both 4 KiB and 16 KiB ARM64 devices.

## Troubleshooting

### Android dependencies are missing

Run `./build-phone.sh setup --download` once, or prepare an already populated
Pico dependency cache with `./build-phone.sh prepare`.

### No compatible JDK was found

Set `JAVA_HOME` to a JDK from version 17 through 21. The wrapper also checks
common Android Studio and system JDK locations.

### ADB cannot find or authorize the phone

Verify USB debugging, unlock the phone, accept the RSA authorization prompt,
and rerun `adb devices`. Use `ANDROID_SERIAL` if multiple devices are listed.

### The APK exists but does not start

Capture the native and Java failure while launching it again:

```bash
"${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}/platform-tools/adb" logcat
```

The package name to filter for is `org.overte.phone`, and the launcher activity
is `org.overte.phone.PermissionsActivity`.
