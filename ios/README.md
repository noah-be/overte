<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Overte for iOS

This directory owns the iPhone and iPad build boundary. The port scope and
architecture decisions are documented in `docs/ios/`.

The supported entry point will be:

```bash
./ios/build-ios.sh doctor
./ios/build-ios.sh bootstrap
./ios/build-ios.sh build --platform simulator
./ios/build-ios.sh test --platform simulator
```

The scripts deliberately refuse to perform signing or installation unless the
caller selects a device operation and supplies the documented external inputs.

