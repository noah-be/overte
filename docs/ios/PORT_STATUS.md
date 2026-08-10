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

The second host-preparation pass additionally provides a fail-closed root
CMake entry, shim-tested build CLI, deterministic simulator selection, strict
bundle metadata validation, cold-start deep-link routing, Linux CI gating,
simulator failure diagnostics, and an offline-verifiable device evidence
format. See `HOST_PREPARATION.md` and `ios/integration-readiness.json`.

The third pass inventories remaining Qt 5, removed Qt 6 audio, Core5Compat,
WebEngine, desktop-framework, and dynamic-plugin debt; generates a deterministic
CycloneDX SBOM; exercises lossless deep-link and lifecycle state machines on the
host; adds accessibility/iPad acceptance cases; and documents the first Xcode
run with machine-readable failure phases.

An isolated Conan recipe resolution on Linux produced a 25-reference arm64
simulator graph after replacing the staged OpenSSL 1.1 dependency with 3.5.7
and moving legacy QuaZIP 1.4 behind the Qt 6 integration gate. The graph audit
now fails on Qt 5, legacy QuaZIP, desktop packages, shared target libraries, or
shader tools placed in the target context.

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
