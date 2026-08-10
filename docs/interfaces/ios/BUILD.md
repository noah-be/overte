# Build Overte for iOS

Run build commands from the repository root on macOS. Start with the complete
[host preparation guide](../../ios/HOST_PREPARATION.md) and
[first Xcode run](../../ios/XCODE_FIRST_RUN.md).

## Bootstrap

```bash
./ios/build-ios.sh bootstrap
./ios/build-ios.sh doctor --platform simulator
./ios/build-ios.sh deps --platform simulator
./ios/build-ios.sh configure --platform simulator
./ios/build-ios.sh build --platform simulator
```

The bootstrap deliberately avoids Qt so Xcode, bundle, lifecycle, signing, and
Metal failures remain separate from the Overte migration.

## Integrated client

The integrated client is pinned to Qt 6.11.1. Host tools and target libraries
must match exactly. Configure explicit target and host roots and validate them
as described in [Qt setup](../../ios/QT_SETUP.md). Then resolve dependencies and
configure the opt-in graph:

```bash
./ios/build-ios.sh deps --platform device
./ios/build-ios.sh configure --platform device --client-graph
cmake --build build-ios/device --config Debug --target Overte
```

Do not substitute desktop Qt, a Linux package, or a simulator-only slice for an
iPhoneOS dependency. The integrated path remains experimental until its open
gates in [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md) close.
