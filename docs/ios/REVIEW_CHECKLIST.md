<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# iOS preparation review checklist

Use this checklist before merging host-preparation changes.

## Scope and build graph

- The default iOS graph remains the minimal UIKit/Metal bootstrap.
- The full client remains opt-in through `OVERTE_IOS_BOOTSTRAP_ONLY=OFF`.
- Apple desktop frameworks and Qt WebEngine are excluded from iOS.
- Device and simulator architecture/deployment settings come from one version contract.
- Signing is off unless a device build receives an explicit development team.

## Dependencies and compliance

- Conan graph audit passes and target libraries are static.
- Qt, MoltenVK, and V8 roots are explicit and contain the required arm64 slice.
- `sbom.cdx.json` is generated from the exact resolved graph.
- Every unresolved license or privacy review item has an owner before release.
- Privacy manifest declarations match runtime observations and Xcode's privacy report.

## Runtime boundaries

- Lifecycle transitions are validated by the portable state-machine tests.
- Cold- and warm-start deep links pass through the bounded allowlisted queue.
- Logs do not contain complete deep links, credentials, or signing material.
- Dynamic Type, VoiceOver, Reduce Motion, safe areas, orientation, pointer, and
  iPad resizing remain in the physical-device matrix.

## Evidence and external actions

- Linux host contracts, shell/Python syntax, and Android regression suites pass.
- The Xcode run follows `XCODE_FIRST_RUN.md` and identifies the exact revision.
- iPhone and iPad device results validate against the checked-in schema.
- Signing, provisioning, upload, and App Store submission are separately approved actions.
