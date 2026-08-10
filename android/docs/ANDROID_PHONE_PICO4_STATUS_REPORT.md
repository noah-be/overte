# Android Phone and Pico 4 Status Report

> **Assessment date:** 2026-08-10
>
> **Scope:** `feature/android-phone-support` and `feature/pico4-support`
>
> **Method:** Read-only source, history, documentation, workflow, and recorded test-result review
>
> **Companion document:** [Android Phone and Pico 4 Roadmap](ANDROID_PHONE_PICO4_ROADMAP.md)

> [!NOTE]
> This report assesses an unofficial, personal, AI-assisted fork maintained as a
> solo hobby project. The maintainer is not part of the official Overte development
> team, the Android Phone and Pico 4 interfaces are not official Overte products,
> and the upstream project's no-AI policy is the reason this work remains clearly
> separated in a fork. References to release readiness describe technical maturity,
> not an obligation or commitment to ship or support a product.

## Executive summary

Neither branch is release-ready today.

- **Android Phone** is a late engineering alpha. It has the stronger build hardening,
  test structure, platform-specific settings cleanup, and package validation. Its
  main blockers are incomplete interactive device validation and a release pipeline
  that is currently blocked and internally inconsistent at the installable-artifact
  handoff.
- **Pico 4** is a feature-rich hardware prototype or early beta. OpenXR, controller
  input, microphone capture, Create, and Android WebView-backed world Web entities
  exist. Its main blockers are roughly 20 application-generated frames per second in
  the measured Hub scene, thermal cutoffs, unfiltered desktop/developer UI, a weaker
  asset-cache extraction contract, and release workflows that have never completed
  end to end on GitHub.
- The branches must be **converged before more large features are added**. They now
  carry overlapping changes in shared Interface, audio, settings, scripts, build,
  and CI code. Continuing independent work increases both merge risk and the chance
  that one client ships stale code from the other.

Recommended release classification:

| Product | Current classification | Release decision |
|---|---|---|
| Android Phone | Late engineering alpha | **No-go for a public alpha** |
| Pico 4 | Functional prototype / early beta | **No-go for a release candidate** |

## 1. Assessment basis

The current remote branch heads were used as the authoritative source:

| Branch | Assessed commit | Relation to `upstream/master` |
|---|---|---:|
| `feature/android-phone-support` | [`2845c3e0b4`](https://github.com/noah-be/overte/commit/2845c3e0b48810382d21cfd0b8064c0e138e5730) | 535 additional commits |
| `feature/pico4-support` | [`cc9ef96b31`](https://github.com/noah-be/overte/commit/cc9ef96b310fd12d3741b026738ba8a1f908c08d) | 397 additional commits |
| `upstream/master` | `b556c57243` | Common upstream ancestor |

No build or test was executed locally as part of this review because the assessment
was explicitly read-only. Statements about successful builds and physical-device
tests therefore distinguish between:

1. current GitHub Actions results;
2. evidence recorded in committed branch documentation; and
3. validation that remains unperformed.

### Local branch state

The local branches do not match their remote counterparts:

- The local Phone branch is nine commits behind the remote Phone branch and has no
  local-only commits.
- The local Pico branch is 28 commits behind the remote Pico branch and four commits
  ahead.
- Two local Pico commits are patch-equivalent to work already present remotely.
- Two local Pico commits are not patch-equivalent and must be preserved and reviewed
  before any local branch reset or replacement:
  - `b49d2750b0` — native coverage workflow and stable headless tests;
  - `31eb8dea8c` — expanded native Android and Pico regression coverage.

## 2. Branch topology and integration risk

The two branches have a common post-upstream merge base from 2026-08-06, but have
diverged rapidly since then:

- 284 commits exist only on the Phone side;
- 146 commits exist only on the Pico side.

A merge simulation identifies 13 high-risk files changed on both sides:

- `.github/workflows/android-phone-release-candidate.yml`
- `android/apps/picoInterface/src/main/java/org/overte/pico/AndroidAudioInput.java`
- `android/apps/picoInterface/src/main/java/org/overte/pico/PermissionsActivity.java`
- `android/apps/picoInterface/src/main/java/org/overte/pico/PicoInterfaceActivity.java`
- `android/build-pico.sh`
- `android/cmake-pico-bootstrap.cmake`
- `android/conan/conanfile-pico.py`
- `interface/src/Application.cpp`
- `interface/src/Application.h`
- `interface/src/ui/ApplicationOverlay.cpp`
- `libraries/audio-client/src/AudioClient.cpp`
- `scripts/system/create/edit.js`
- `scripts/system/settings/Settings.qml`

The Pico application subtree carried by the Phone branch is stale. Comparing
`android/apps/picoInterface` between the two heads produces 25 changed files, with
2,185 insertions and 634 deletions. The Pico subtree in the Phone branch must not be
used as the authoritative Pico implementation during integration.

The apparent branch size is inflated by large nightly reports and repeated
serverless-world fixtures. That is a maintenance and review problem by itself, but
it does not remove the genuine shared-code integration risk.

### Recommended source ownership during convergence

| Area | Authoritative source during integration |
|---|---|
| Pico OpenXR, WebView, input, and Pico runtime | Current Pico branch |
| Phone app, 16 KiB build path, Phone UI selectors, Phone test infrastructure | Current Phone branch |
| Shared Interface, audio, settings, and scripts | Manual reconciliation |
| Pico subtree embedded in the Phone branch | Do not use as the Pico baseline |
| Local-only Pico coverage commits | Preserve, review, then reapply intentionally |

## 3. Android Phone status

### 3.1 Product and platform shape

The Phone client is implemented as a distinct Android product rather than a lightly
renamed VR package:

- application ID `org.overte.phone`;
- ARM64 production target and x86_64 emulator variant;
- minimum API 26, target and compile SDK 36;
- GLES 3.2 and touchscreen required;
- microphone hardware declared optional;
- landscape orientation;
- `overte:` and `hifi:` deep-link handling;
- exported launcher but non-exported Qt-native activity;
- Android backup and data transfer disabled;
- limited permission set: network, audio, and vibration only.

The client uses a 2D OpenGL display path and touchscreen virtual controls. It does
not require or load an OpenXR runtime.

### 3.2 Build and package maturity

The Phone build and package path is one of the strongest parts of the branch:

- dedicated 16 KiB-compatible Qt and non-Qt dependency graphs;
- fail-closed dependency readiness sentinels;
- ELF load-segment and ZIP alignment checks;
- APK/AAB content checks;
- package-permission and metadata contracts;
- deterministic, checksum-verified dependency restore;
- source revision, package, ABI, SDK, digest, and signer-state manifests;
- CycloneDX and provenance preparation;
- no default repository release key;
- explicitly unsigned store-neutral release candidates.

The public Phone v2 dependency archive was documented as successfully restored in
an empty Ubuntu 24.04 container. The aggregate device-free regression gate was also
documented as passing after this restore.

### 3.3 Runtime and application surface

The default startup set is deliberately small. It includes:

- request and progress services;
- touchscreen virtual pad;
- Phone action bar;
- Phone tablet app registration;
- native-QML emotes;
- Shield/Bubble;
- People/PAL;
- Avatar;
- Places;
- Quick Go To.

The screen-space action bar exposes Go To, Tablet, first-/third-person view, and
mute. The retained tablet applications cover the core explore/social experience:

- Audio;
- Settings;
- Menu;
- Shield;
- People;
- Avatar;
- Places;
- Home and Tutorial;
- Emote.

Create, More/Community, the legacy Users surface, and remote Web applications are
not enabled.

### 3.4 Settings and UI cleanup

Phone-specific QML selectors provide a relatively strong fail-closed policy:

- Graphics is not constructed;
- Controls is not shown;
- General Settings admits only `Navigation` and `Mouse Sensitivity`;
- HMD, Snapshots, Plugins, Privacy, and desktop UI options are excluded;
- Audio hides VR mode, redundant mode tabs, keyboard push-to-talk, and avatar audio
  tools;
- Avatar hides dominant hand, HMD alignment, and the external avatar marketplace;
- Security hides scripting-plugin management.

This is the right direction: a category is admitted only when its complete contract
is meaningful on a phone.

### 3.5 Tests and recorded physical validation

The current [`Android tests` workflow](https://github.com/noah-be/overte/actions/runs/31331344600)
passes at the assessed branch head. Its high-level jobs include:

- fast host tests;
- architecture and security contracts;
- JVM and native host coverage;
- complete device-free regression.

Extended mutation, stability, and endurance tiers are not run on every push.

Committed device evidence reports:

- successful ARM64 APK build;
- 106 packaged native libraries, all reachable by the runtime closure audit;
- 16 KiB ELF alignment passing;
- launch, deep link, repeated lifecycle, and Back smoke tests passing;
- a five-minute physical-device graphics run at 29.74 FPS against an internal
  30 FPS target;
- 10.89 ms GPU time and 6.12 ms batch time;
- 97.64% overlay-cache hit rate after warm-up;
- low reported Android thermal status during that short test.

These results are useful but do not constitute a current-head, signed-candidate,
human-observed acceptance test. They cover one device and a short duration.

### 3.6 Phone release blockers and defects

#### RC environment rejection

The latest [Phone release-candidate run](https://github.com/noah-be/overte/actions/runs/31331373667)
passed tag, version, and contract preflight. GitHub rejected the build job before it
started because `feature/android-phone-support` was not allowed to deploy to the
`android-phone-release-candidate` environment.

This is a workflow-dispatch and repository-environment problem, not a compilation
failure. The preferred correction is tag-only dispatch with the environment limited
to protected release tags, rather than broadly allowing the mutable feature branch.

#### Emulator acceptance cannot install the RC artifact

The release workflow deliberately produces:

`phoneInterface-release-unsigned.apk`

The emulator-acceptance workflow instead expects:

`phoneInterface-release.apk`

It then attempts to install that artifact through ADB. This is invalid for two
independent reasons:

1. the file name does not match the uploaded artifact;
2. the store-neutral APK is intentionally unsigned and therefore not installable as
   a normal Android package.

The acceptance design should be split into:

- an installable x86_64 debug/instrumentation lane for Android runtime behavior;
- an acceptance lane that consumes the exact signed artifact produced by an
  authorized distribution channel.

#### Manual workflow registration is incomplete

Only the Phone release-candidate stub is registered on the repository default
branch. The manual Phone trusted-build and emulator-acceptance workflows are absent
from the repository workflow list.

#### Interactive product validation is incomplete

The following remain unvalidated or only source-contract-tested:

- successful, invalid, cancelled, and domain login;
- Android IME resizing, focus, and Back behavior;
- microphone allow and deny paths;
- audio input/output enumeration, routing, mute, and sliders;
- slow, offline, and federated Places behavior;
- People actions and domain transitions;
- Avatar bookmarks, wearables, and error recovery;
- network loss and reconnect;
- Wi-Fi/mobile handoff;
- extended background/foreground and process recreation;
- Adreno and Mali coverage;
- notch, hole-punch, rounded, and asymmetric displays;
- 30–60 minute populated-domain thermal, battery, network, audio, and touch soak.

#### Permission timing

`RECORD_AUDIO` is requested before the user reaches the world. Denial does not block
the client, but a just-in-time request when voice is first enabled would reduce
onboarding friction and provide clearer context.

## 4. Desktop and VR residue in Android Phone

The visible UI cleanup is substantial, but the shared package and architecture
still contain residue.

### 4.1 Visible or policy-level residue

- Unsupported menu entries may still be displayed with “Unavailable on Android”
  instead of being removed.
- Menu filtering depends on English display labels and a regular expression for
  `HMD`, `VR`, and `Desktop`.
- Localization or label changes can therefore alter the platform security policy.
- Native developer and crash actions still exist in the binary; normal Phone menu
  navigation filters them out, but the guard is primarily presentational.

### 4.2 Packaged but normally unreachable residue

- Generic Oculus, Steam, HMD, desktop, and WebEngine QML remains in the shared
  resource bundle.
- Graphics and controller QML remains in the script payload even though Phone does
  not instantiate those pages.
- The script packaging rules remove developer, community, tutorial, simplified UI,
  and selected legacy assets, but they are not yet a complete reachability allowlist.
- OAuth, Backtrace, and related BuildConfig endpoints remain empty.

### 4.3 Architectural residue

- The Phone target directly uses an override located in the Pico application tree:
  `android/apps/picoInterface/overrides/OffscreenGLCanvas.cpp`.
- The Phone branch carries a stale Pico application implementation.
- A temporary legacy 4 KiB dependency escape hatch still exists for development,
  although the release gates reject it.

### 4.4 Features that should remain explicit Phone non-goals by default

- HMD and tracked-controller settings;
- desktop windows and native desktop file dialogs;
- Oculus or Steam platform login;
- Sixense, Leap Motion, Perception Neuron, and similar legacy controller pages;
- desktop snapshot directories;
- crash and developer menus;
- unrestricted plugin management;
- unbounded rendering and resolution controls.

### 4.5 Potential Phone parity features requiring product decisions

- touch-owned Create;
- snapshots implemented through Android storage/media APIs;
- More/Community with provenance, signature, origin, and sandbox policy;
- external avatar marketplace;
- portrait support;
- supported script-app installation;
- crash reporting and telemetry policy.

## 5. Pico 4 status

### 5.1 Product and platform shape

The Pico client is a dedicated ARM64 VR package:

- application ID `org.overte.pico`;
- minimum API 26, compile SDK 36, target SDK 35;
- GLES 3.2 and Android VR headtracking required;
- PICO VR launcher category and `pvr.app.type=vr`;
- OpenXR display and input path;
- controller, hand, tracker/XDev, haptic, refresh-rate, swapchain, and lifecycle
  handling;
- tablet, HUD, locomotion, teleport, and spatial interaction;
- Near Grab and Far Grab;
- Create;
- Android `AudioRecord` microphone backend;
- Android WebView-backed world Web entities.

The default rendering profile is intentionally conservative: 80% OpenXR render
scale, a 72 Hz runtime profile, forward rendering, reduced LOD, and most expensive
effects disabled.

### 5.2 Functional surface

The Pico startup set is much broader than Phone and includes:

- tablet UI;
- menu;
- Away;
- Shield/Bubble;
- People/PAL;
- Avatar;
- Settings;
- user connection support;
- Places;
- notifications and dial tone;
- tablet positioning;
- first-person HMD support;
- Create in a separate script engine;
- controller scripts.

Local Near/Far Grab fixtures, depth control, release, and basic laser states have
been manually accepted. Microphone telemetry has also been exercised on hardware.

### 5.3 Device-free tests and CI

The current [Pico device-free CI run](https://github.com/noah-be/overte/actions/runs/31331220986)
passes. The test catalog covers approximately 30 entries spanning:

- OpenXR loader, display, and input source contracts;
- Android `AudioRecord` state and transport;
- WebView JNI and touch-state contracts;
- Create message validation;
- tablet lifecycle and settings;
- APK, build, release, and acceptance contracts;
- shell and workflow behavior.

The coverage map links eleven risk capabilities to tests. It is a useful ownership
map, but it is not line coverage and does not exercise Qt, OpenXR, Android WebView,
or physical input at runtime.

No GitHub run exists for:

- Pico 4 trusted build;
- Pico 4 release candidate;
- Pico 4 device acceptance.

The repository therefore has no current remote evidence that a clean checkout can
restore dependencies, build the APK, sign an RC, create the draft, and accept that
exact artifact on hardware.

### 5.4 Pico release blockers and defects

#### Application-generated frame rate

The final repeated A/B measurement at the recommended 80% profile reports:

| Metric | Result |
|---|---:|
| XR compositor present rate | 71.84 FPS |
| New-frame rate | 19.86 FPS |
| Render rate | 19.72 FPS |
| Game-loop rate | 46.72 FPS |
| Overte process CPU | 293% |

The compositor remains close to 72 presents per second through reprojection, while
Overte supplies only about 20 new frames per second. The branch documentation
identifies the Hub scene as CPU-limited. This is a release blocker for interaction
latency and comfort unless a lower application rate is explicitly accepted through
measured product criteria.

#### Thermal stability

A requested five-minute microphone/render test reached the safety threshold after
76 seconds at 90.55 °C CPU. A later requested 60-second integration run reached the
threshold after 58 seconds at 90.1 °C CPU. Audio remained valid until shutdown, so
the result indicates a rendering/system-load limit rather than microphone failure.

#### Asset-cache extraction

The Pico extractor currently:

- concatenates destination paths directly;
- does not canonicalize or enforce root containment;
- uses the youngest file timestamp as the cache identity;
- does not reject duplicate or unsafe manifest paths;
- can miss content changes that preserve a timestamp;
- does not remove assets deleted by a newer package.

Because the manifest is package-owned, this is not by itself proof of a remotely
exploitable vulnerability. It is nevertheless an update-integrity, robustness, and
supply-chain hardening gap.

#### Unfiltered desktop and developer UI

Pico Settings currently exposes:

- General;
- Graphics;
- Audio;
- Controls;
- Pico Interaction;
- Security;
- QML Allowlist;
- Script Security.

General Settings includes User Interface, Mouse Sensitivity, HMD, Snapshots,
Privacy, and Plugins. Controller Settings includes Desktop Movement, Game
Controller, Sixense, Perception Neuron, Leap Motion, and OSC in addition to VR
Movement.

The inherited native menu constructs `Developer > Crash` unconditionally because
the intended environment check is replaced with `result = true`. The menu contains
intentional deadlock, abort, double-free, null-dereference, and other crash actions.
Pico starts `system/menu.js` and has no Phone-style root filter. These actions must
therefore be treated as potentially reachable in the production tablet until a
hardware UI check proves otherwise. Regardless of visibility, they should be
compile- or capability-guarded before release.

#### Unbounded graphics controls

The Pico Settings application exposes both Pico render scale and generic desktop
render controls:

- performance presets from Low Power through High/Custom;
- local lights, Bloom, and custom shaders;
- deferred rendering;
- shadows and ambient occlusion;
- field of view from 20° to 130°;
- generic resolution scale from 0.1 to 2.0.

These controls can invalidate the measured thermal/render profile. Pico needs a
small set of validated presets and a recoverable safe default.

#### Web-entity compatibility limits

The Android WebView bridge supports ordinary DOM hover, click, drag, scroll, opaque
and transparent content, and integration with the shared world-Web renderer.

Known limits include:

- 10 Hz capture;
- maximum 2048-pixel edge;
- roughly 36 MiB for three ARGB frame copies at the maximum 4:3 capture size;
- no `scriptURL` integration;
- no Qt WebChannel;
- no bidirectional EventBridge;
- no guarantee for video, WebGL, or heavy animation;
- external-network behavior not yet accepted as a product path.

#### Create qualification

Create is available and selected message boundaries are tested. Full qualification
still requires Entity List, import, domain entities, both hands, tracking loss,
rapid target changes, inherited off-hand rotation, mirror/secondary camera, and
long editing sessions.

## 6. Desktop, Quest, and legacy VR residue in Pico

Pico carries substantially more inherited UI and payload than Phone:

- the startup selector remains named `+android_questInterface`;
- the default startup script adds `Debug defaultScripts.js` under Developer;
- Oculus login and account QML remains packaged;
- Oculus, Vive, Index, SteamVR, and OpenVR device names remain in settings and
  plugin paths;
- Desktop Tablet Scale, 3D mouse cursor, reticle, mini tablet, laser/mallet
  keyboard, and stylus preferences remain available;
- desktop snapshot directory selection remains available;
- crash-reporting and Discord controls can be shown even though Breakpad and the
  Android service configuration are empty or no-op;
- developer, community, and tutorial scripts are copied wholesale;
- Qt Contacts, DocGallery, Organizer, Feedback, and Versit libraries are staged;
- the documented APK size is roughly 550 MB;
- visibility of `Pico Interaction` is inferred from a user setting rather than a
  stable platform capability;
- Pico replaces `Application_Setup.cpp` with a 2,271-line copy, despite only a
  relatively small Pico-specific delta.

Some generic OpenXR and external-controller code may be intentionally portable. It
should still be governed by an explicit supported-capability list rather than by
accidental inheritance from Desktop or Quest.

## 7. Platform-appropriate feature parity

Feature parity should not mean copying every Desktop function to every Android
client. The appropriate goal is equivalent completion of the platform's intended
user journeys.

| Capability | Android Phone | Pico 4 | Remaining gate |
|---|---|---|---|
| World loading and rendering | Present | Present | Live-domain, failure, reconnect testing |
| Navigation | Touch pad, Places, deep links | Locomotion, teleport, Places | Long-session hardware testing |
| Account and domain login | Present | Present | Real accounts, errors, IME/domain flow |
| Audio and voice | Present, reduced UI | AudioRecord with AEC/NS | Routing, speech quality, echo, duration |
| People and Avatar | Present | Present | Multiavatar and live-domain acceptance |
| Core tablet apps | Deliberately reduced | Broad inherited set | Capability inventory and cleanup |
| Settings | Mostly Phone-specific | Desktop-heavy | Pico fail-closed policy |
| Create | Deliberately disabled | Present, partly tested | Phone redesign; Pico hardware acceptance |
| World Web content | Deliberately absent | Partial Android WebView bridge | WebChannel/origin policy decision |
| Lifecycle | Deep-link/Back/background code | XR and Activity lifecycle code | Real suspend/resume/eviction tests |
| Performance | Short 30 FPS target passed | About 20 new FPS | Product target and Pico optimization |
| Release automation | Advanced but blocked/inconsistent | Designed but never run | End-to-end workflow execution |
| Distribution | F-Droid-first concept | Several possible channels | Ownership, signing, portal decisions |

### Recommended mandatory Phone parity

- account and domain login;
- world, Avatar, Audio, People, and Places;
- touch navigation and camera control;
- core tablet applications;
- secure settings and script policy;
- deep links, Back, and Android lifecycle;
- network transition and reconnect;
- reproducible, installable release handoff.

### Recommended optional Phone scope

- touch-owned Create;
- Community/More;
- snapshots;
- portrait;
- external avatar marketplace;
- controller support;
- managed script installation.

### Recommended mandatory Pico parity

- complete XR input and lifecycle behavior;
- an explicit native-frame/reprojection comfort target;
- safe tracking-loss and controller state;
- audio and speech quality;
- core tablet apps;
- Create fundamentals;
- spatial Web interaction;
- thermally stable long sessions;
- signed and hardware-accepted RC.

### Recommended optional Pico scope

- WebChannel/EventBridge;
- body/XDev trackers as supported product features;
- mirror and secondary camera;
- external OpenXR controllers;
- Community/script marketplace.

## 8. Prioritized findings

| Priority | Finding | Product impact | Primary resolution |
|---|---|---|---|
| P0 | Branch divergence and stale cross-client code | Integration regressions and duplicated work | Create one integration branch now |
| P0 | Phone RC environment rejection | No RC build | Tag-only dispatch and environment correction |
| P0 | Phone acceptance expects/install unsigned wrong-name APK | Acceptance path cannot work | Split emulator and signed-artifact lanes |
| P0 | Pico produces about 20 new FPS | Comfort and interaction risk | CPU profiling and hardware optimization loop |
| P0 | Pico reaches thermal cutoff | Long-session safety/stability risk | Reduce CPU/load and validate automatic fan behavior |
| P0 | Pico developer/crash actions potentially reachable | Intentional production crashes | Native capability/compile guard |
| P1 | Pico asset extraction is timestamp/path based | Update and integrity risk | Shared content-addressed safe extractor |
| P1 | Pico settings expose Desktop and legacy controllers | Confusing/no-op or harmful UX | Fail-closed capability model |
| P1 | Pico trusted/release/device workflows never ran | Release chain unproven | Configure runners/secrets and execute gates |
| P1 | Phone interactive device coverage is incomplete | User-facing regressions remain likely | Adreno/Mali and UI-flow matrix |
| P1 | Full-file `Application_Setup` fork | Ongoing drift and merge cost | Extract platform hooks |
| P2 | Large unused script/QML/library payloads | APK size, review, attack surface | Reachability allowlists and package trimming |
| P2 | Large committed nightly logs and duplicate fixtures | Review and maintenance cost | Move evidence to artifacts/compact reports |
| P2 | Startup microphone permission | Onboarding friction | Just-in-time voice permission |

## 9. Immediate next actions

Before adding large features:

1. Preserve the two local-only Pico coverage commits.
2. Freeze feature development on the two divergent product branches.
3. Create a common integration branch from the current Pico remote head.
4. Import Phone changes by owned area rather than using the stale Phone-side Pico
   subtree.
5. Repair Phone workflow registration, tag dispatch, and artifact handoff.
6. Make Pico developer/crash actions fail closed.
7. replace Pico's asset-cache extraction with a shared safe implementation.
8. Establish explicit Phone and Pico product-parity contracts.
9. Run device correctness gates before tuning behavior from assumptions.
10. Do not create a Pico RC until frame generation and thermal stability meet agreed
    hardware criteria.

## 10. Release-readiness conclusion

### Android Phone

**No-go for public alpha today.** The engineering foundation is strong, especially
the 16 KiB build path, package gates, dependency restore, and platform-specific UI
filtering. Release automation cannot yet produce and accept an installable final
artifact, and the main user journeys have not been completed on a representative
device matrix.

### Pico 4

**No-go for release candidate today.** The feature breadth is substantial, but the
measured application frame rate, thermal cutoff, potentially reachable crash menu,
desktop-heavy settings, and unexecuted release chain are hard blockers.

### Overall

The next phase should prioritize convergence, capability-driven product surfaces,
workflow correctness, and hardware evidence. New large features such as Phone
Create or Pico WebChannel should begin only after those foundations are stable.

The actionable milestone sequence, dependency graph, ownership split, and release
gates are maintained in the companion
[Android Phone and Pico 4 Roadmap](ANDROID_PHONE_PICO4_ROADMAP.md).
