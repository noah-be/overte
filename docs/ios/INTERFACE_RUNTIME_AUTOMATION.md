<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Interface runtime automation

The iOS runtime tiers consume an already built, numbered Full Client artifact.
They never accept `OverteIOSBootstrap` as Interface evidence and never rebuild a
candidate while testing it. The candidate manifest, producer run, source
revision and SHA-256 are verified before a simulator or physical device is
queried. The workflow always executes the reviewed harness from its dispatch
revision; the candidate revision is treated only as untrusted artifact data and
is never checked out on the protected iPad runner.

Candidate verification includes the main executable's Mach-O load commands.
Only Apple system frameworks and `/usr/lib` may remain dynamically linked; the
audited oneTBB and WebRTC audio-processing recipes produce static archives.
Absolute Conan build RPATHs, `@rpath` third-party dylibs, or `/lib` load paths
fail before simulator installation, evidence collection, or iPad handoff.

`ios/tests/interface-runtime-automation.json` is the machine-readable boundary.
Host contracts remain the broad deterministic regression tier. Simulator and
iPad execution initially share the strongest existing end-to-end oracle: six
ordered native gates from the real domain handshake through EntityTree decode
and renderer handoff.

GitHub exposes `workflow_dispatch` only after a workflow definition exists on
the repository default branch. These harnesses are therefore prepared on
`apple-ios`, but cannot be dispatched until their workflow files are merged to
the default branch. This is an activation boundary, not runtime evidence.

## Simulator tier

`.github/workflows/ios-world-runtime.yml` is called only by the reviewed
`ios-bootstrap.yml` gate after the complete host suite. The explicit
`[ios-worlds]` commit marker (or `world_evidence` dispatch input) provisions
independent arm64 `iphonesimulator` Qt, JITless V8, Conan and MoltenVK slices,
builds the real `Overte` target and packages a numbered simulator candidate.
Validated Qt, V8 and Conan outputs are saved immediately as both exact caches
and provenance-bound durable artifacts. Cacheable Qt, V8 and client compiler
outputs are also written to remote sccache storage as each translation unit
finishes.

The runtime gate installs that exact app separately on iPhone and iPad
simulators. Each family loads the bundled
`file:///~/serverless/tutorial.json` scene and the current `hifi://overte_hub`
online place. The serverless case requires an import-commit marker followed by
a populated EntityTree and renderer handoff. The online case resolves the
active place through the metaverse API immediately before launch and requires
the connected DomainList UUID to equal the resolved domain UUID, in addition
to all six network/entity gates. A screenshot is retained only after those
gates pass; its PNG structure, digest, dimensions and visible image variation
are validated. The final evidence-set report binds all four screenshots to the
candidate SHA-256 and source revision and rejects byte-identical serverless and
online frames. Raw unified logs remain private scratch data and are deleted.

`.github/workflows/ios-interface-simulator-acceptance.yml` remains available as
a manual consumer for an already published simulator candidate. Its older
six-gate route is useful for generic entity acceptance, but the world workflow
is the stronger named-destination and screenshot oracle.

## Physical iPad tier

`.github/workflows/ios-ipad-runtime-acceptance.yml` is also manual. Its first
job verifies a pre-signed `iphoneos` candidate without touching a device. The
execution job additionally requires:

- approval through the protected `ios-ipad-device-acceptance` environment;
- the self-hosted labels `macOS`, `ARM64` and `overte-ios-ipad`;
- confirmation equal to `INSTALL <candidate-sha256>`;
- one runner-local mode-0600 device-identifier file; and
- an unlocked, paired iPad in Developer Mode.

The device identifier is masked before `devicectl` runs and is never copied to
evidence. The runner preflights the installed Xcode command help, chooses only
the configured iPad, verifies the code signature plus profile team, bundle,
entitlements, expiry and fixed-device authorization, then installs and launches with a
bounded console capture, and requires the same six entity gates. Raw console,
device JSON, provisioning data and the signed app are removed from the private
scratch directory and are never uploaded. The installed app is intentionally
left on the iPad for follow-up inspection; the next launch uses
`--terminate-existing`.

This first automated hardware tier proves install/launch, real network/domain
traffic, EntityQuery/data, a populated EntityTree and renderer handoff. It does
not prove that the resulting domain is the named deep-link destination, pixel
correctness, or the complete 22-case physical-device matrix. Audio routing,
microphone consent, VoiceOver, pointer input, Split View, network loss,
memory/thermal endurance and pixel correctness still require dedicated XCTest,
controlled peripherals or reviewed evidence. The existing
`validate-device-results.py` continues to require one complete iPhone result
and one complete iPad result before full device acceptance.

## Candidate production boundary

The automated iPad workflow requires an already signed package produced by the
protected `package-client` path. No such protected signed producer exists in
the current workflow set; adding one is an explicit prerequisite. A
Sideloadly-modified local IPA is suitable for
personal installation, but it is not a provenance-bound CI candidate because
re-signing changes its digest. No Apple credential, private key, profile or
device identifier belongs in this repository or a public workflow artifact.
