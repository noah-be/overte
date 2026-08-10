<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# iOS port preparation status

## Implemented

- iOS 17 deployment and Xcode/iOS SDK 26 version contract;
- separate arm64 device and arm64 simulator Conan profiles;
- static native iPhone/iPad bootstrap app with modern scene lifecycle;
- interactive connection preview with a tested Overte address parser, saved
  destination, text input, deep-link consumption, and live place resolution
  through the Overte directory API;
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
- unsigned macOS 26 CI for arm64 device-SDK compilation plus iPhone and iPad
  simulator launch tests; and
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

The credential-free cloud pipeline passed on source revision
`a0fb187efea53821bf2ed7a4988bca78efbc1046` in
[GitHub Actions run 31363636498](https://github.com/noah-be/overte/actions/runs/31363636498)
using Xcode 26.6 and the iOS 26.5 SDK. It compiled and validated an unsigned
arm64 `iphoneos` bundle, compiled and embedded `default.metallib`, launched the
app for at least five seconds on both iPhone and iPad simulators, and produced
an unsigned simulator archive. The downloaded archive passed ZIP integrity and
SHA-256 manifest verification; its digest was
`a3b08e5d7a08e15af1d0a2646b90960e48eb8cdb95e3d62765e10aa053e1671a`.

The Linux iOS host contracts and the Android `fast` regression tier also pass
in this worktree.

## Remaining hosted macOS integration work

- resolve and patch failures in each target dependency recipe;
- compile the shared Overte client with Qt 6 and finish the Qt Multimedia
  migration;
- build and validate the static non-JIT V8 archive;
- compare MoltenVK with the Metal reference workload; and
- generate Xcode's aggregated privacy report.

The next implementation sequence is maintained in `ITERATION_PLAN.md`. The
connection preview intentionally exposes the boundary between working place
resolution and the not-yet-linked domain UDP protocol instead of presenting a
false successful connection.

## Requires explicitly approved physical-device access

- rendering, audio, microphone, touch, lifecycle, thermal, and memory tests;
- development signing and provisioning; and
- the device-only acceptance matrix.

App Store submission remains outside the autonomous preparation workflow.
