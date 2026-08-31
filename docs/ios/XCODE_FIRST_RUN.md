<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# First Xcode run

This is the exact handoff from host-only preparation to the first Apple-toolchain
run. Do not enable signing for the simulator tier and do not treat a bootstrap
launch as full-client acceptance.

## 1. Record the environment

Use a clean macOS host with Xcode 26 or newer. Check out this branch without
local build products, then record `git rev-parse HEAD`, `sw_vers`,
`xcodebuild -version`, and `xcrun --sdk iphonesimulator --show-sdk-version` in
the run notes. Run:

```bash
./ios/build-ios.sh bootstrap
source build-ios/tooling-venv/bin/activate
./ios/build-ios.sh doctor --platform simulator
./ios/tests/run-tests.sh
```

If Qt, MoltenVK, or V8 packages are supplied, point their explicit environment
roots at audited iOS packages and add `--require-qt`, `--require-moltenvk`, and
`--require-v8`. Never fall back to host packages.

## 2. Resolve and build in layers

```bash
./ios/build-ios.sh deps --platform simulator
./ios/build-ios.sh configure --platform simulator
cmake --build build-ios/simulator --config Debug --target OverteIOSBootstrap
./ios/ci/verify-app.sh build-ios/simulator/ios/Debug-iphonesimulator/OverteIOSBootstrap.app
./ios/ci/simulator-smoke.sh build-ios/simulator/ios/Debug-iphonesimulator/OverteIOSBootstrap.app
```

Preserve `build-ios/simulator/conan/graph.json` and `sbom.cdx.json`. After the
bootstrap succeeds, opt into the experimental full-client graph in a separate
build directory with `-DOVERTE_IOS_BOOTSTRAP_ONLY=OFF`. Fix one failure class at
a time; never weaken an iOS exclusion just to advance configuration.

## 3. Classify failures

Match the earliest causal error to a phase in `ios/first-run-triage.json`.
Attach the command, complete log, source revision, Xcode/SDK versions, target
(simulator or device), and the smallest relevant CMake cache excerpt. Remove
tokens, signing material, usernames, and absolute home paths before sharing.

For crashes, retain the `.crash` report, simulator console excerpt, screenshot,
and reproduction sequence. For dependency failures, retain the Conan graph node
and package options. A later linker error is not useful until the earlier
compile or recipe error is resolved.

## 4. Exit criteria

The first-run gate closes only when both iPhone and iPad simulator launches pass,
the expanded bundle validator passes, no forbidden desktop framework or dynamic
library enters the app, and the produced evidence names the exact commit. Device
signing, privacy aggregation, thermal behavior, audio routing, and physical-device
acceptance remain separate external gates.
