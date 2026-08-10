# Android Platform Ownership and Boundary Report

> **Assessment date:** 2026-08-10
>
> **Baseline:** `android-main` at `f0fe27e666080a09dbc78ed2920184feb01be03d`
>
> **Scope:** Android Phone, shared Android, standalone Android VR, Pico 4, and Quest
>
> **Method:** Local source, build graph, manifest, test, workflow, and UI review

## Purpose

This document maps the integrated Android tree to the long-lived branch structure:

```text
main
└── android-main
    ├── android-phone
    └── android-vr
        ├── android-vr-pico
        └── android-vr-quest
```

The branches are integration and development lanes, not separate source packages.
It is normal for `main` and `android-main` to contain every Android application.
Ownership answers where a change should start and which gates must pass; it does
not require deleting sibling product code from a branch.

This is an unofficial, AI-assisted hobby fork maintained by one person. The goal
is a useful, enjoyable client on more devices, not a commercial support promise or
an official Overte platform interface.

## Executive assessment

The repository already has distinct Phone, Pico, Quest, and legacy Android app
targets, but its architectural boundaries are less mature than its product names:

- Phone and Pico use modern Gradle 8.13, Java 17, NDK 27, and dedicated settings
  files. Quest and the legacy Android interface still require Gradle 6.5 and old
  Android SDK baselines.
- Pico is the only modern standalone-VR implementation. It has its own OpenXR
  provider, display/input plugins, loader, WebView bridge, audio capture, and
  device-free suite.
- Quest is not currently a Pico-equivalent OpenXR product. It still uses the
  proprietary Oculus Mobile activity and plugin path, SDK 28, legacy storage
  permissions, and a very small host-test surface.
- Phone is a genuine 2D product with its own launcher, deep links, touch UI,
  screen-space tablet, emulator path, 16 KiB dependency graph, and broad tests.
- Shared Interface and library files contain substantial Pico-branded behavior.
  Some behavior is truly generic Android/VR work; some is Pico policy living in
  global files; and some is generic behavior whose diagnostics were simply named
  after the first hardware used to test it.
- Settings are partially capability-driven for Phone, but Pico visibility still
  relies on a mutable setting (`deferTabletCreationUntilOpen`) as a platform proxy.
- Test coverage is strong for Phone and Pico. V1 adds one shared hardware-free
  Android-VR gate; Quest modernization still lacks a modern product build and
  hardware acceptance loop.

The correct strategy is gradual extraction with tests, not history rewriting or a
large attempt to make each branch contain only platform-specific files.

## Current product targets

| Product | Module | Toolchain | Runtime path | Current ownership |
|---|---|---|---|---|
| Modern Android Phone | `phoneInterface` | Gradle 8.13, SDK 36, Java 17 | Qt 5 + 2D OpenGL + touch | `android-phone` |
| Pico 4 | `picoInterface` | Gradle 8.13, SDK 35/36, Java 17 | Qt 5 + OpenXR | `android-vr-pico` |
| Quest | `questInterface` | Gradle 6.5, SDK 28, Java 8 | Oculus Mobile SDK | `android-vr-quest` |
| Legacy Android VR/interface | `interface` | Gradle 6.5, SDK 26 | Legacy Qt/Android VR | Reference/migration source |
| Shared Android libraries | `qt`, common C++/Java helpers | Mixed | Used by multiple apps | `android-main` |
| Shared standalone-VR layer | Not yet a coherent module | Mixed | OpenXR/controllers/VR UI | `android-vr` |

## Recommended source ownership

### `android-main`

Changes should start here when they are useful to both 2D and VR Android clients:

- Android toolchain policy and reproducible dependency conventions;
- shared Qt Android runtime packaging;
- JNI compatibility exports;
- safe asset extraction and cache publication;
- common Activity state, permission, and restart policies where behavior matches;
- generic Android lifecycle, audio, network, and filesystem adaptations;
- the Android module inventory and cross-product security contracts.

The first concrete extraction is complete on the working branch:
`QtInputConnectionCompat.cpp` now has one implementation under `android/common` and
is compiled by both Phone and Pico. A3 also places the modern Android
`OffscreenGLCanvas.cpp` and shared Qt/TBB runtime overrides under `android/common`;
Phone no longer compiles or packages anything from the Pico product directory.

### `android-phone`

- `android/apps/phoneInterface` product behavior;
- Phone launcher, deep links, predictive Back, and screen-space presentation;
- Phone-specific QFileSelector resources and default scripts;
- touch controls, Phone tablet registration, and Phone emotes;
- Phone 16 KiB packaging, emulator acceptance, release metadata, and device tests;
- Phone-only rendering policies such as the screen-space overlay cache.

### `android-vr`

This layer should own behavior that applies to more than one standalone Android
headset, even if Pico is initially the only working implementation:

- OpenXR loader and extension negotiation abstractions;
- generic OpenXR instance/session/space/event policies;
- generic pose, action, haptics, and controller-state representation;
- VR Activity lifecycle contracts independent of vendor intent categories;
- common VR tablet placement, laser/pointer behavior, and safe interaction presets;
- headset-independent device test protocols and acceptance-result schemas.

Moving code here must follow a second-consumer rule: extract a component when its
contract is demonstrably vendor-neutral or when Quest work actually needs it. Do
not rename every Pico file pre-emptively.

### `android-vr-pico`

- Pico manifest metadata and `com.picovr` launcher category;
- Pico package ID, signing, release, and device-acceptance workflows;
- Pico runtime quirks and verified extension requirements;
- Pico controller bindings or thresholds that are hardware-specific;
- Pico power, thermal, graphics, microphone, and unattended-device tooling;
- diagnostic test stations intended specifically for Pico 4.

### `android-vr-quest`

- Quest manifest and Meta store/runtime requirements;
- Quest/Touch controller bindings and hardware validation;
- migration away from the legacy Oculus Mobile implementation;
- Quest-specific signing, packaging, entitlement, and device workflows;
- compatibility decisions that genuinely require Meta APIs.

## Boundary inventory

The source scan found 122 files with generic Android references, 44 with Phone
references, 45 with Pico references, and 91 with Quest/Oculus references. Counts
include build and UI references and are indicators, not measures of code quality.

High-coupling files touching two or more product boundaries include:

- `interface/src/Application.cpp`
- `interface/src/Application_Setup.cpp`
- `interface/src/Application_Events.cpp`
- `interface/src/Application_UI.cpp`
- `interface/src/ui/LoginDialog.cpp`
- `libraries/shared/src/shared/FileUtils.cpp`
- `scripts/system/create/edit.js`
- `cmake/macros/AutoScribeShader.cmake`
- `android/apps/phoneInterface/CMakeLists.txt`
- `android/apps/phoneInterface/build.gradle`

These files should not be split merely because they contain multiple macros. They
should be changed only when a small policy, hook, or service can be extracted and
covered independently.

## Important coupling problems

### P0 — Incorrect or fragile platform identity

1. **Pico Settings detection used mutable state at the assessed baseline.** A2 on
   `refactor/android-platform-boundaries` replaces it with fail-closed
   `SettingsTouchConfiguration` profiles selected from the compiled
   `HIFI_ANDROID_APP` identity. Only `android_picoInterface` enables and constructs
   Pico Interaction; Phone, Quest, Desktop, and unknown profiles keep it disabled.
2. **Generic Android paths emit Pico-branded diagnostics.** Keyboard, audio,
   entity loading, graphics, menu, and lifecycle code contain `PICO_*` log markers
   under generic `Q_OS_ANDROID` paths. This makes Quest/Phone diagnosis misleading
   and obscures which behavior is actually Pico-only.
3. **Phone consumed Pico-owned paths at the assessed baseline.** A3 on
   `refactor/android-platform-boundaries` moves `OffscreenGLCanvas.cpp` and the
   common Qt/TBB runtime override directory under `android/common`. Both product
   builds now consume that neutral path, and an inventory contract rejects future
   Phone CMake/Gradle references to Pico or Quest product directories. The immutable
   `pico4-deps-v1` release archive retains its historical layout, so the verified
   download path copies that payload into the shared directory after extraction.

### P0 — Quest is a legacy product, not an empty modern target

Quest currently has:

- Gradle 6.5 and Android Gradle Plugin 4.1.3;
- compile/target SDK 28;
- Java 8 source compatibility;
- obsolete read/write external-storage permissions;
- implicit exported-component behavior;
- a proprietary Oculus Mobile renderer and Activity;
- no Quest-equivalent device-free OpenXR suite.

The first Quest milestone must decide between modern OpenXR reuse and continued
Oculus Mobile maintenance. For a solo hobby fork, modern OpenXR reuse is the lower
maintenance direction, provided a Quest device can eventually validate it.

### P1 — Pico overrides are too large

Pico replaces complete shared sources, including `Application_Setup.cpp`, rather
than injecting small policies or hooks. Full-file forks are difficult to review,
easy to leave stale, and make common Interface changes expensive. Extraction
should begin with narrowly testable decisions, not a single rewrite of the entire
override.

### P1 — UI remains desktop/VR-history driven

- Phone has strong selector-based filtering, but some shared UI still contains
  Oculus, HMD, Desktop, filesystem, and plugin concepts.
- Pico exposes a dedicated interaction page from a shared Settings root without a
  reliable platform capability.
- Shared login QML and C++ retain Oculus-account flows inherited from the desktop
  and old Quest product.
- Several scripts use Pico names for behavior that may become generic VR behavior,
  including tablet placement, pointers, and Create interaction.

The desired parity is outcome parity, not identical Desktop UI. Unsupported actions
should be absent or fail closed rather than remain visible as historical residue.

### P1 — Test topology does not match branch topology

- `android/tests/suite/catalog.json` provides strong shared and Phone gates.
- `pico4-test-suite.py` provides 30 Pico device-free tests; V1 selects its sixteen
  parent-relevant runtime tests through the shared Android catalog.
- Robolectric covers launcher behavior for Interface, Phone, Pico, and Quest.
- Quest has no modern build, OpenXR, interaction, packaging, or device-free suite.
- CI workflow names and triggers still describe individual historical branches,
  not the new integration hierarchy.

The suites do not need to be rewritten immediately. The V1 `android-vr` catalog
tier aggregates shared policy evidence while leaving release and hardware gates in
their product lanes.

## Settings and interface residue

| Surface | Residue or risk | Correct owner / action |
|---|---|---|
| Shared Settings home | Baseline selected Pico page through mutable setting | A2 complete: immutable QFileSelector profile; `android-main` + `android-vr` |
| General Preferences | Desktop Movement, VR hardware/plugins, filesystem and Oculus options remain in shared graph | Capability filtering; platform branches |
| Login | Oculus account creation/linking remains in shared C++ and QML | Keep only for a product that supports it |
| Pico Interaction | Vendor name is valid today, but several thresholds describe generic ray/grab behavior | Keep Pico-owned until a second headset uses the contract |
| Create | Pico mapping names and validation are embedded in shared scripts | Extract generic interaction policy only when Quest consumes it |
| Tablet | Pico message channel and diagnostics are embedded in shared scripts | Define a generic VR tablet contract, retain vendor diagnostics separately |
| Keyboard | Generic Android code emits Pico markers | Rename generic diagnostics; guard real Pico behavior |
| Audio | Generic Android lifecycle and Pico microphone transport are interleaved | Separate transport policy from Android recorder lifecycle |

## Branch-to-test ownership

| Branch | Required hardware-free gates | Hardware gate when available |
|---|---|---|
| `android-main` | Android fast, contracts, Robolectric, JVM/JS/native coverage | One Phone plus one headset smoke session after high-risk changes |
| `android-phone` | Android fast/host, Phone contracts, emulator where prepared | Phone smoke, microphone, deep link, lifecycle |
| `android-vr` | Android contracts, Pico device-free suite, generic OpenXR native tests | At least one supported headset |
| `android-vr-pico` | Pico 30-test suite, project quick suite, Pico packaging contracts | Pico acceptance, microphone, world loading, thermal/performance |
| `android-vr-quest` | Quest launcher policy, future OpenXR/build/package contracts | Quest install, launch, tracking, input, audio, sustained session |
| `main` | All changed-platform hardware-free gates | Targeted release-candidate sessions only |

## Merge policy

1. Begin work on the lowest branch that owns the behavior.
2. Merge stable device work upward to its parent integration branch.
3. Merge parent changes downward before starting dependent child work.
4. Require the parent's tests plus the changed child's tests.
5. Do not cherry-pick the same logical change independently into siblings.
6. Keep old feature branches as read-only references until the new lanes have
   completed several successful integration cycles.
7. Avoid force-pushes and history rewriting on the new hierarchy.

## Recommended immediate direction

Continue with small shared extractions that already have two consumers. The first
shared JNI source, immutable Settings capability boundary, neutral Android override
ownership, and aggregate Android-VR gate are complete on the working branch. Next,
extract one small OpenXR policy with a vendor-neutral contract. Defer the
large OpenXR/Quest design until the current iOS integration is stable and Quest
hardware is available for a real validation loop.
