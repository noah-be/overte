# Overte for iPhone and iPad

> [!CAUTION]
> This is an AI-assisted experimental port. It is incomplete and has not
> completed the security, privacy, performance, and physical-device acceptance
> required for production use. Review the current status before using valuable
> accounts or distributing an application.

## Current status

The product goal is the complete Overte Interface on iPhone and iPad. The
currently validated developer path is a smaller native UIKit and Metal bootstrap
that tests the Apple toolchain, bundle, lifecycle, deep links, place resolution,
and basic platform integration. It is not the complete Overte client and does
not yet connect to a domain protocol endpoint.

The integrated Qt/Overte client is an explicit experimental porting path. Its
Qt 6 migration and native dependency graph still have open build gates and it is
not an accepted device build.

## Support matrix

| Area | Current configuration |
| --- | --- |
| Build host | macOS with Xcode 26 or newer |
| Target OS | iOS 17 deployment target |
| Architecture | arm64 simulator and arm64 device profiles |
| Virtual target | iPhone and iPad Simulator bootstrap |
| Physical target | iPhone and iPad; explicit signing and acceptance required |

Linux can run repository contracts but cannot establish an iOS build, launch,
signing result, or native ABI compatibility.

## Validated bootstrap path

```bash
./ios/build-ios.sh bootstrap
./ios/build-ios.sh doctor --platform simulator
./ios/build-ios.sh build --platform simulator
./ios/build-ios.sh test --platform simulator
```

This path keeps `OVERTE_IOS_BOOTSTRAP_ONLY=ON` and prevents unfinished desktop
dependencies and dynamic plug-ins from entering the build.

## Experimental integrated-client path

The integrated client requires audited iOS Qt and Conan packages. Follow
[BUILD.md](BUILD.md) and opt into the client graph only in a separate build
directory. A configured or compiled target is not device acceptance.

## Output, installation, and launch

Simulator builds are unsigned. Device builds can produce an unsigned IPA for
inspection or a developer-signed app when an explicit team and bundle ID are
provided. Build scripts never install an app implicitly. A developer may either
package a locally signed build on a Mac or verify an unsigned CI artifact before
using the separately authorized Sideloadly signing and installation path. See
[Developer artifacts](RELEASE.md) for the local installation boundary.

## Known limitations

- The bootstrap resolves places but does not send Overte domain protocol packets.
- The integrated client has not completed Qt, V8, MoltenVK, rendering, or native
  dependency integration.
- Physical iPhone and iPad acceptance evidence remains external.
- App Store submission is not part of the current milestone.

## Documentation

- [Roadmap and current milestone](ROADMAP.md)
- [Complete build guide](BUILD.md)
- [Testing](TESTING.md)
- [Touch UI architecture and validation](TOUCH_UI.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [Security and privacy](SECURITY_AND_PRIVACY.md)
- [Continuous integration](CI.md)
- [Development status](DEVELOPMENT_STATUS.md)
- [Developer artifacts](RELEASE.md)
