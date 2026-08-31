# Overte for Android phones

> [!CAUTION]
> This is an AI-assisted experimental port. It has not completed the device
> coverage, security review, performance validation, or release testing required
> for production use. Review the source before using valuable accounts or
> distributing the application.

## Current status

The `phoneInterface` module packages Overte's mono 2D renderer and touchscreen
input as the independent `org.overte.phone` application. It targets
landscape-oriented 64-bit Android phones running Android 8/API 26 or newer and
targets API 36. Portrait, 32-bit devices, broad GPU compatibility, and store
publication are outside the current milestone.

## Support matrix

| Area | Current configuration |
| --- | --- |
| Build host | 64-bit Linux |
| Target OS | Android API 26 minimum, API 36 target |
| Production architecture | ARM64 with verified 16 KiB-compatible dependencies |
| Emulator | x86_64 AVD, API 35 default |
| Physical target | ARM64 touchscreen phone; Adreno and Mali coverage still required |

## Normal developer setup

Run from `android/`:

```bash
cd android
./build-phone.sh doctor
./build-phone.sh setup --download
```

This restores checksum-verified shared and Phone-specific dependencies and
builds the debug APK. The multi-hour dependency producer path is maintainer work
and is documented separately in [BUILD.md](BUILD.md).

## Emulator tests

```bash
cd android
./phone-emulator-test.sh doctor
./phone-emulator-test.sh all
```

The emulator build is x86_64 and cannot be confused with the ARM64 production
APK.

## Output, installation, and launch

The debug APK is
`android/apps/phoneInterface/build/outputs/apk/debug/phoneInterface-debug.apk`.
Install and start it on an explicitly selected phone with:

```bash
cd android
ANDROID_SERIAL=<serial> ./build-phone.sh deploy
```

## Known limitations

- Normal APKs are ARM64-only and require the dedicated verified 16-KiB graph.
- A successful emulator run does not prove graphics, audio, lifecycle, page-size,
  thermal, or vendor behavior on a physical phone.
- Microphone denial is supported, but privacy and security review is incomplete.
- Current artifacts are for developer installation and testing, not publication.

## Documentation

- [Roadmap and current milestone](ROADMAP.md)
- [Complete build guide](BUILD.md)
- [Testing](TESTING.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Security and privacy](SECURITY_AND_PRIVACY.md)
- [Continuous integration](CI.md)
- [Development status](DEVELOPMENT_STATUS.md)
- [Developer artifacts](RELEASE.md)
