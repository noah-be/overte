# Build Overte for Android phones

The complete existing command reference remains
[`android/ANDROID_PHONE_BUILD.md`](../../../android/ANDROID_PHONE_BUILD.md). Run
its commands from `android/` on a 64-bit Linux host.

## Requirements

- JDK 17 through 21
- Android SDK Platform 36 and Build Tools 36.0.0
- Android NDK 27.3.13750724
- CMake 3.31.6, Ninja, Conan 2, Python, Perl, and Git
- ADB for physical installation

Android Studio is optional.

## Normal developer path

```bash
cd android
./build-phone.sh doctor
./build-phone.sh setup --download
./build-phone.sh build
```

The download path restores the pinned dependency graph. The APK build fails
closed if the dedicated Phone outputs are missing, stale, incomplete, or not
16-KiB compatible.

## Dependency-maintainer path

`build-phone.sh deps`, `build-phone-qt-16k.sh`,
`prepare-phone-16k-conan-deps.sh`, and `phone-prebuilt-16k-deps.sh export` are
artifact-producer operations. They require substantial time, disk, memory, and
swap and are not part of ordinary onboarding. Follow the ordered procedure in
the detailed guide and never publish an archive without its content-bound
verification marker and checksum manifest.
