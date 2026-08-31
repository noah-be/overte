<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Overte iOS port scope

This document is the executable scope contract for the first Overte client on
iPhone and iPad. Work outside this contract must not delay the first usable
client.

## Baseline

| Item | Initial contract |
| --- | --- |
| Build host | macOS with Xcode 26 or newer |
| Build SDK | iOS 26 SDK or newer |
| Deployment target | iOS and iPadOS 17.0 |
| Device architecture | arm64 |
| Simulator architecture | arm64 |
| UI toolkit | Qt 6.11 or newer compatible release |
| Form factors | iPhone and iPad |
| Graphics | Vulkan through MoltenVK or native Metal, selected by a measured spike |
| Packaging | Statically linked application bundle |

The deployment target may only be raised after a documented compatibility
review. Versions are centralized in `ios/versions.env` so CI and local builds
cannot silently diverge.

## First usable client

The first usable client must:

1. install and launch on a supported iPhone and iPad;
2. survive foreground, background, interruption, and memory-warning events;
3. authenticate and connect to an Overte domain;
4. download and render a representative world and avatar;
5. provide touch movement, camera control, and text entry;
6. play spatial audio and capture microphone input after consent;
7. reconnect after a temporary network interruption; and
8. keep its writable files inside Apple-provided application containers.

## Deferred capabilities

The following capabilities are explicitly deferred until the first usable
client passes its acceptance matrix:

- OpenXR, OpenVR, Oculus, Steam, Sixense, Kinect, Leap Motion, and Neuron;
- desktop launchers, auto-update, installers, and server processes;
- desktop-only window management and system tray integration;
- arbitrary dynamically loaded native plug-ins;
- camera capture, haptics, and background audio modes; and
- App Store submission and production signing.

Deferring a capability means the iOS build must disable it explicitly. Silent
fallbacks that leave unreachable code or unsigned dynamic libraries in the app
bundle are not acceptable.

## Acceptance tiers

### Host tier

Runs on Linux and macOS without Xcode. It checks repository contracts, plist
contents, dependency policy, CMake routing, scripts, and generated metadata.

### Simulator tier

Runs unsigned on a macOS CI runner. It configures, builds, verifies, launches,
and terminates the application in at least one iPhone and one iPad simulator.

### Device tier

Runs only with explicit signing credentials and installation approval. It
checks launch, rendering, touch, audio, microphone consent, lifecycle, network
recovery, memory use, and thermal behavior on physical hardware.

## Completion gates

Preparation is complete when:

- `ios/build-ios.sh doctor` diagnoses a clean Xcode environment;
- dependency resolution succeeds independently for device and simulator;
- CMake generates an Xcode project without macOS-only targets;
- an unsigned simulator bundle builds reproducibly in CI;
- the host and simulator tiers are green;
- signing inputs are documented and never stored in the repository; and
- every device-only assertion is listed in the device acceptance procedure.
