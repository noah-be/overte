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

`build-ios.sh` configures the repository root with
`OVERTE_IOS_BOOTSTRAP_ONLY=ON`. This fail-closed default prevents the unfinished
desktop-client dependency and dynamic plug-in graph from entering an iOS build.
The full integrated client may only be explored explicitly with
`-DOVERTE_IOS_BOOTSTRAP_ONLY=OFF`; it is not an acceptance target yet.

The scripts deliberately refuse to perform signing or installation unless the
caller selects a device operation and supplies the documented external inputs.

Version 0.2 is an interactive connection preview. It accepts an Overte place,
`hifi://` address, or incoming deep link and resolves named places through the
real Overte directory service. It deliberately reports direct domain targets
without sending protocol packets until the audited domain networking core is
linked in the next integration stage.
