# Overte for Pico 4

> [!CAUTION]
> This is an AI-assisted experimental port. It may be incomplete,
> insufficiently tested, insecure, or unsuitable for valuable accounts and
> production use. Review the current status before installing or distributing
> the application.

## Current status

The Pico 4 port has a maintained Linux command-line build, checksum-verified
dependencies, an install/deploy path, device-free regression tests, and separate
release-candidate and headset-acceptance workflows. It remains experimental and
does not have complete worn-headset, security, privacy, comfort, or store
acceptance evidence.

## Support matrix

| Area | Current configuration |
| --- | --- |
| Build host | 64-bit Linux; Fedora, Debian/Ubuntu, Arch, and openSUSE bootstrap paths |
| Target | Pico 4 |
| Target architecture | ARM64 |
| Virtual target | No emulator acceptance path |
| Physical target | Authorized USB-connected Pico 4 |

## Quick start

```bash
cd android
./build-pico.sh doctor
./build-pico.sh bootstrap --with-deps
./build-pico.sh
```

The bootstrap may request administrator access and Android SDK license
acceptance. `doctor` is the read-only entry point.

## Output, installation, and launch

The debug APK is written below
`android/apps/picoInterface/build/outputs/apk/debug/`. To build, install, and
start it on an explicitly selected authorized headset:

```bash
cd android
ANDROID_SERIAL=<serial> ./build-pico.sh deploy
```

## Known limitations

- The normal developer path depends on large prebuilt Android packages.
- Device-free tests do not prove OpenXR, controller, rendering, audio, thermal,
  or comfort behavior on a worn headset.
- Store and direct-distribution requirements remain partly portal-dependent.
- Release publication is limited to a verified draft candidate and an explicitly
  approved device-acceptance handoff.

## Documentation

- [Complete build guide](BUILD.md)
- [Testing](TESTING.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Security and privacy](SECURITY_AND_PRIVACY.md)
- [Continuous integration](CI.md)
- [Development status](DEVELOPMENT_STATUS.md)
- [Developer artifacts](RELEASE.md)
