<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Host-only iOS preparation

This document separates repository preparation that is valid on Linux from
claims that require Apple's compiler, simulator runtime, signing services, or
physical hardware. The authoritative gate inventory is
`ios/integration-readiness.json`.

## Completed without a Mac

- isolated worktree and feature branch;
- fail-closed root CMake bootstrap graph for iOS;
- numeric Xcode, SDK, CMake, Python and Conan tool contracts;
- deterministic arm64 simulator and device profiles;
- build CLI tests using controlled replacements for Xcode, `xcrun`, CMake and
  Conan;
- native UIKit/Metal shell, scene lifecycle, cold- and warm-start deep-link
  routing, app-container paths, audio-session observers and network monitoring;
- iPhone/iPad, safe-area, orientation and touch probes;
- static dependency classification and explicit exclusion of desktop-only
  modules, plus an isolated 25-reference Conan recipe resolution with a
  fail-closed graph auditor;
- centralized Qt 5/6 CMake helpers and iOS WebEngine guards;
- explicit MoltenVK and non-JIT V8 package boundaries;
- PrivacyInfo, entitlements, bundle metadata and arm64 requirements;
- host-testable bundle and device-result validators;
- independent Linux CI contracts plus unsigned macOS simulator CI with failure
  screenshots and console logs; and
- signing, privacy, rendering and device acceptance handoff gates.

The extended pass also adds a regression-checked full-client compatibility-debt
inventory, deterministic CycloneDX SBOM generation, portable lifecycle and
bounded deep-link state machines, accessibility/iPad acceptance probes, static
V8 and MoltenVK slice checks, and the first-Xcode-run/review handoff in
`XCODE_FIRST_RUN.md`, `COMPLIANCE.md`, and `REVIEW_CHECKLIST.md`.

Run every Linux-verifiable preparation check with:

```bash
./ios/tests/run-tests.sh
python3 -m py_compile ios/tools/*.py ios/tests/*.py ios/conanfile.py
bash -n ios/build-ios.sh ios/ci/*.sh ios/tests/run-tests.sh
conan inspect ios --format=json
git diff --check
```

## Why the remaining gates cannot be closed here

An iOS SDK is more than headers: the build must use Apple's Clang driver,
platform linker, Metal compiler, asset compiler, bundle tools and simulator
runtime. Qt, V8, MoltenVK and every native dependency must contain compatible
iPhoneOS and/or iPhoneSimulator arm64 slices. Linux archives or successful host
syntax checks cannot establish those ABI properties.

Likewise, GPU timing, thermal pressure, microphone routing, background
suspension, memory warnings, signing and privacy aggregation are runtime or
Apple-service observations. The repository now defines inputs, commands,
thresholds and evidence formats for those steps, but deliberately does not
manufacture passing evidence.

The experimental full-client graph remains opt-in with
`OVERTE_IOS_BOOTSTRAP_ONLY=OFF`. Its first Apple-toolchain run is expected to
drive the remaining Qt 6 API migration, static plug-in registration and native
dependency recipe work in the order recorded by the readiness inventory.
