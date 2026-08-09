<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# iOS port preparation status

## Implemented

- iOS 17 deployment and Xcode/iOS SDK 26 version contract;
- separate arm64 device and arm64 simulator Conan profiles;
- static native iPhone/iPad bootstrap app with modern scene lifecycle;
- Info.plist, App Icon, launch configuration, entitlements, ATS policy, deep
  links, and PrivacyInfo.xcprivacy;
- Metal reference pipeline, touch probe, safe-area layout, network reachability,
  motion capability, audio-session interruption, and route-change handling;
- centralized Qt 5/Qt 6 CMake helpers and Qt 6 iOS component selection;
- iOS Qt WebView selector and desktop Qt WebEngine exclusion;
- explicit non-JIT V8 runtime and package contract;
- explicit MoltenVK device/simulator XCFramework selection;
- classified staged dependency graph with host shader tools separated from
  target libraries;
- unsigned macOS 26 simulator CI for iPhone and iPad launch tests; and
- machine-readable host and physical-device acceptance contracts.

## Verified without Apple hardware

The iOS host contracts, plist parsing, dependency classification, shell syntax,
Python syntax, and workflow YAML parse pass on Linux. The existing Android host
suite passed its harness, native, and JavaScript tiers; its Robolectric tier was
blocked by the host providing Java 25 instead of its required Java 21.

## Requires a macOS/Xcode execution environment

- compile and launch the bootstrap on the macOS 26 CI image;
- resolve and patch failures in each target dependency recipe;
- compile the shared Overte client with Qt 6 and finish the Qt Multimedia
  migration;
- build and validate the static non-JIT V8 archive;
- compare MoltenVK with the Metal reference workload; and
- generate Xcode's aggregated privacy report.

## Requires explicitly approved physical-device access

- rendering, audio, microphone, touch, lifecycle, thermal, and memory tests;
- development signing and provisioning; and
- the device-only acceptance matrix.

App Store submission remains outside the autonomous preparation workflow.

