# Build Overte for Android phones

The complete existing command reference remains
[`android/phone/docs/BUILD.md`](../../../android/phone/docs/BUILD.md). Run
its commands from `android/phone/` on a 64-bit Linux host.

## Requirements

- JDK 17 through 21
- Android SDK Platform 36 and Build Tools 36.0.0
- Android NDK 27.3.13750724
- CMake 3.31.6, Ninja, Conan 2, Python, Perl, and Git
- ADB for physical installation

Android Studio is optional.

## Normal developer path

```bash
cd android/phone
./build.sh doctor
./build.sh setup --download
./build.sh build
```

The download path restores the pinned dependency graph. The APK build fails
closed if the dedicated Phone outputs are missing, stale, incomplete, or not
16-KiB compatible.

## Dependency-maintainer path

`build.sh deps`, `build-phone-qt-16k.sh`,
`prepare-phone-16k-conan-deps.sh`, and `phone-prebuilt-16k-deps.sh export` are
artifact-producer operations. They require substantial time, disk, memory, and
swap and are not part of ordinary onboarding. Follow the ordered procedure in
the detailed guide and never publish an archive without its content-bound
verification marker and checksum manifest.
