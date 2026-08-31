# iOS developer artifacts

The current goal is to create verifiable applications that a developer can sign,
install, and test. App Store publication is out of scope.

Simulator output is unsigned and can be launched by the simulator smoke script.
The device path can package an unsigned IPA plus a JSON manifest and SHA-256
metadata. It never installs the application automatically.

## Locally signed bootstrap

For a locally signed device build, supply the same explicit development team and
bundle identifier to both the build and package commands:

```bash
./ios/build-ios.sh build \
  --platform device \
  --bundle-id org.example.overte \
  --development-team TEAMID

./ios/build-ios.sh package \
  --platform device \
  --bundle-id org.example.overte \
  --development-team TEAMID
```

The package command verifies the existing signed bundle and provisioning
metadata before creating the IPA. The script deliberately does not select a
device or install it; use an explicitly authorized Apple development tool and
device outside the build command.

## Unsigned CI handoff

The unsigned device-SDK artifact proves compilation and package structure only.
Verify its manifest and SHA-256 before transferring it. The documented
Windows-VM route uses Sideloadly with the developer's own authorized Apple
account to apply a Personal Team signature and install it on the selected test
device. That route is for iterative development, not distribution.

Follow [`docs/ios/SIGNING_AND_DEVICE_TESTS.md`](../../ios/SIGNING_AND_DEVICE_TESTS.md)
and [`docs/ios/IPAD_REMOTE_TESTING.md`](../../ios/IPAD_REMOTE_TESTING.md) for the
signing boundaries, artifact verification, installation handoff, and device
evidence. A successful package, signature, or installation is not physical-device
acceptance.
