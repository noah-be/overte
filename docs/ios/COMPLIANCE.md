<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Dependency, license, and privacy evidence

`./ios/build-ios.sh deps --platform simulator` writes the audited Conan graph and
a deterministic CycloneDX 1.6 SBOM to
`build-ios/simulator/conan/{graph.json,sbom.cdx.json}`. Generate the device graph
separately; do not infer that a simulator artifact proves a device slice exists.

The SBOM separates target components from build tools and carries the repository's
license/privacy review state. Before release, resolve every direct dependency
reported as unresolved, archive its license text and source offer obligations,
and reconcile the final embedded components with the built `.app`. A generated
SBOM is inventory evidence, not legal approval.

Privacy review uses three sources together: `PrivacyInfo.xcprivacy`, Xcode's
aggregated privacy report, and an observed runtime network trace covering cold
launch, domain connection, microphone permission, background/foreground, and
deep-link entry. Any new SDK or endpoint reopens the review. Store evidence with
the source revision, Xcode/SDK versions, platform, and reviewer; remove personal
data and secrets before retention.
