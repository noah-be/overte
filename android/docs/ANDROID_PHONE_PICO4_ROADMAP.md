# Android Phone and Pico 4 Roadmap

> **Roadmap status:** Proposed
>
> **Assessment baseline:** 2026-08-10
>
> **Detailed evidence:** [Android Phone and Pico 4 Status Report](ANDROID_PHONE_PICO4_STATUS_REPORT.md)

> [!IMPORTANT]
> This is a personal roadmap for an unofficial, AI-assisted fork. The maintainer is
> currently a solo hobby developer, is not part of the official Overte development
> team, and is not presenting Android Phone or Pico 4 as official Overte interfaces.
> The upstream project has a no-AI policy; this fork exists so AI-assisted work stays
> clearly separate. The goal here is not a perfect commercial product. It is to build
> something useful and fun that works well enough for more people to experience
> Overte on more devices.

## 🎯 Project compass

1. **Working beats perfect.** Prioritize joining a domain, moving, interacting,
   communicating, and returning for another session.
2. **One maintainer means one focus.** Reduce branch drift and maintenance burden
   before expanding the feature surface.
3. **Test what can hurt the experience.** Crashes, broken input, data loss, unusable
   frame rate, overheating, and misleading controls matter more than process polish.
4. **Parity means the same useful outcome, not the same Desktop UI.** A Phone or Pico
   workflow may be smaller and platform-native.
5. **Sharing is optional and incremental.** A sideloadable APK for interested testers
   is already a meaningful success; stores and formal release automation can wait.
6. **Upstream boundaries stay explicit.** Fork branding and documentation should
   prevent users from mistaking these builds for officially supported Overte clients.

## 🧭 At a glance

| Product area | Android Phone | Pico 4 | Practical next proof |
|---|---|---|---|
| Core runtime | 🟡 Functional alpha | 🟡 Functional prototype | Representative hardware acceptance |
| Build hardening | 🟢 Strong | 🟡 Good local evidence | Clean trusted-build execution |
| UI/platform fit | 🟢 Mostly Phone-specific | 🔴 Desktop/legacy UI exposed | Capability-driven UI |
| Automated tests | 🟢 Broad device-free suite | 🟡 Good source-contract suite | Runtime/emulator coverage |
| Performance | 🟡 30 FPS short-run evidence | 🔴 About 20 new FPS | Agreed sustained performance target |
| Thermal stability | 🟡 Short run only | 🔴 Safety cutoff reached | 30–60 minute automatic-fan soak |
| Build sharing | 🔴 Blocked/inconsistent | 🟡 Designed, never completed | Produce and sideload a known APK |
| Distribution | 🟡 F-Droid-first idea | 🔴 Not selected | Optional later; direct APK is enough initially |

### Current usability verdict

| Product | Verdict | Why |
|---|---|---|
| 📱 Android Phone | **Promising personal alpha** | Fix APK handoff, then test the core journey on a few real phones |
| 🥽 Pico 4 | **Useful prototype** | Improve frame rate/thermal behavior and remove dangerous or irrelevant UI |

## Legend

| Symbol | Meaning |
|---|---|
| 🟢 | Complete or strong evidence exists |
| 🟡 | Partially complete; important validation remains |
| 🔴 | Blocking defect or missing gate |
| 🤖 | Can be completed by the solo maintainer with code, CI, or an emulator |
| 👤 | Requires a personal scope choice or repository configuration |
| 📱 | Requires physical Android phone hardware |
| 🥽 | Requires physical Pico 4 hardware |
| 🔐 | Optional publishing work: signing, protected environments, or a store |

## 🚦 Critical path

```mermaid
flowchart LR
    A0["A0 🤖 Preserve branch state"] --> A1["A1 🤖 Converge branches"]
    A1 --> A2["A2 🤖 Shared Android platform layer"]
    A1 --> A3["A3 🤖 Capability-driven UI"]
    A1 --> A4["A4 🤖 Repair workflow code"]
    A2 --> A5["A5 🤖 Automated parity gates"]
    A3 --> A5
    A4 --> S1["S1 👤 Share a test APK"]
    B0["B0 👤 Choose personal scope"] --> A3
    B0 --> F1["F1 🤖 Add chosen optional features"]
    A5 --> H1["H1 📱 Phone acceptance"]
    A5 --> H2["H2 🥽 Pico correctness acceptance"]
    H2 --> H3["H3 🥽 Pico performance and thermal gate"]
    S1 --> H1
    S1 --> H2
    H1 --> R1["R1 🔐 Optional Phone publishing"]
    H3 --> R2["R2 🔐 Optional Pico publishing"]
    F1 --> H1
    F1 --> H2
```

The critical rule is simple: **avoid maintaining the same major feature twice.
Converge first, then build the fun parts against one shared mobile baseline.**

## 🔥 P0 — Do next

These are the highest-value next actions for one maintainer. They are ordered to
produce a usable result early, not to satisfy a formal release process.

| Order | Action | Mode | Exit condition |
|---:|---|---|---|
| 1 | Preserve the two local-only Pico coverage commits | 🤖 | No local test work can be lost during branch synchronization |
| 2 | Choose one integration branch for all new work | 👤 | The old feature branches become reference points |
| 3 | Create a shared integration baseline from current Pico | 🤖 | Both products are represented in one branch |
| 4 | Resolve shared Interface/audio/settings/build ownership | 🤖 | Both device-free suites pass from the same tree |
| 5 | Repair Phone artifact naming/signing/install handoff | 🤖 | A locally or CI-built APK can actually be installed |
| 6 | Disable Pico production developer/crash actions | 🤖 | Actions are not constructible or triggerable in production |
| 7 | Replace Pico's timestamp/path asset extraction | 🤖 | Both clients use one safe content-addressed contract |
| 8 | Pick the next personally valuable Phone/Pico outcomes | 👤 | A short Now / Later / Maybe list prevents scope drift |
| 9 | Try the core journey on available and volunteer hardware | 📱 + 🥽 | Major blockers are recorded with simple reproduction steps |
| 10 | Improve Pico frame rate and thermal behavior iteratively | 🤖 + 🥽 | Sessions are comfortable and stable enough to enjoy |

## Workstreams

| Workstream | Goal | Main milestones |
|---|---|---|
| 🌿 Convergence | One authoritative mobile code line | A0, A1 |
| 🧱 Platform architecture | Shared safe Android foundations | A2 |
| 🎛️ Device UI | Only meaningful and safe controls are exposed | A3, B0 |
| 🧪 Quality | Cheap automated checks plus focused device sessions | A5, H1, H2, H3 |
| ⚙️ Builds | Repeatable, installable APKs; publishing is optional | A4, S1, R1, R2 |
| 📦 Footprint | Smaller packages and review surface | A6 |
| ✨ Useful parity | Chosen platform-appropriate outcomes | F1 |

---

## Autonomous milestones

The milestones in this section can be completed without physical hardware or a new
scope choice. Builds and host/emulator tests are part of their definition of
done where the existing toolchain is available.

### A0 🤖 — Preserve and baseline

**Objective:** Make integration safe before changing branch topology.

#### Deliverables

- [ ] Preserve `b49d2750b0` and `31eb8dea8c` under explicit backup refs.
- [ ] Record the authoritative Phone and Pico remote SHAs.
- [ ] Record the current passing GitHub Actions runs.
- [ ] Create a file-ownership map for shared conflict areas.
- [ ] Mark the Phone-side Pico subtree as non-authoritative.
- [ ] Define the integration branch naming and merge policy.

#### Exit gate

> All unique work is recoverable, source ownership is explicit, and the maintainer
> no longer needs to commit new work to either old feature branch.

### A1 🤖 — Converge into one mobile integration branch

**Objective:** Build both Android products from one authoritative tree.

#### Integration policy

| Area | Integration rule |
|---|---|
| Pico OpenXR/WebView/input/runtime | Keep current Pico implementation |
| Phone app/16 KiB/UI/tests | Import current Phone implementation |
| Shared Interface/audio/settings/scripts | Reconcile manually by behavior |
| Phone-side stale Pico files | Never choose automatically during conflict resolution |
| Local Pico coverage work | Reapply only after review against the integrated tests |

#### Deliverables

- [ ] Create the integration branch from current `feature/pico4-support`.
- [ ] Import the Phone application and Phone-only resources.
- [ ] Resolve the 13 shared high-risk files deliberately.
- [ ] Keep Phone and Pico package IDs and build targets isolated.
- [ ] Run Phone device-free tests.
- [ ] Run Pico device-free tests.
- [ ] Run shared project/native host tests where configured.
- [ ] Document any intentional platform exceptions.

#### Exit gate

> Both clients configure and pass their complete device-free gates from one branch,
> with no stale cross-client implementation selected by accident.

### A2 🤖 — Create a shared Android platform layer

**Objective:** Replace copy-based and cross-product coupling with small, tested
platform services.

#### Deliverables

- [ ] Introduce a shared content-addressed asset-cache extractor.
- [ ] Canonicalize and constrain every extracted path.
- [ ] Reject unsafe, duplicate, unsorted, empty, and oversized manifest entries.
- [ ] Extract into a versioned directory and publish it atomically.
- [ ] Safely remove obsolete cache versions.
- [ ] Add interruption and upgrade-recovery tests.
- [ ] Move `OffscreenGLCanvas` into a shared Android override.
- [ ] Remove the Phone target's dependency on a Pico-named override.
- [ ] Replace Pico's 2,271-line `Application_Setup.cpp` fork with small hooks or
  platform policies.
- [ ] Share lifecycle, permission, and Activity-state helpers where behavior is
  truly identical.

#### Exit gate

> Shared Android behavior has one implementation, Pico-specific behavior is small
> and explicit, and update/cache behavior is deterministic across both apps.

### A3 🤖 — Make the UI capability-driven and fail closed

**Objective:** Expose only controls that are meaningful, tested, and safe for the
selected product.

#### Foundation

- [ ] Define stable platform capability IDs.
- [ ] Stop using translated display strings or regular expressions as policy keys.
- [ ] Enforce capabilities in native action handlers as well as QML presentation.
- [ ] Add regression tests for every hidden or disabled capability.

#### Android Phone cleanup

- [ ] Remove unsupported menu rows rather than suffixing them with “Unavailable”.
- [ ] Prevent direct invocation of unsupported native menu actions.
- [ ] Keep Graphics and controller graphs unconstructed.
- [ ] Audit packaged QML and scripts against actual routes.
- [ ] Keep HMD, Desktop, plugin, and crash actions explicit non-goals.

#### Pico cleanup

- [ ] Hide or remove Desktop Movement.
- [ ] Hide Sixense, Perception Neuron, Leap Motion, and unsupported controllers.
- [ ] Remove Oculus platform-login UI unless explicitly supported.
- [ ] Remove desktop snapshot-directory controls.
- [ ] Remove/no-op crash-reporting and Discord controls until configured.
- [ ] Compile- or capability-guard Developer and Crash menus.
- [ ] Remove `Debug defaultScripts.js` from production startup.
- [ ] Replace setting-based Pico detection with an immutable platform capability.
- [ ] Replace unbounded Graphics controls with validated presets and safe recovery.

#### Exit gate

> Every visible setting and action works on the current platform, and unsupported
> actions cannot be triggered through QML, scripts, localization, or direct menu APIs.

### A4 🤖 — Repair CI/CD workflow code

**Objective:** Make the repository workflows internally coherent before protected
environments, signing keys, or hardware are attached.

#### Android Phone

- [ ] Register trusted-build and emulator workflows on the default branch.
- [ ] Require release-candidate dispatch from an immutable Phone tag.
- [ ] Keep unprivileged tag/version preflight ahead of protected jobs.
- [ ] Split x86_64 debug/instrumentation acceptance from signed-channel acceptance.
- [ ] Stop treating the unsigned store-neutral APK as installable.
- [ ] Contract-test artifact names, ABI, digest, debug state, and signing state.
- [ ] Ensure release and acceptance workflows consume exactly the artifact they
  describe.

#### Pico 4

- [ ] Add an unprivileged tag/ref preflight before the signing runner.
- [ ] Ensure mutable refs cannot reach release secrets or execute on the release
  runner.
- [ ] Contract-test trusted build, RC, draft release, and device handoff together.
- [ ] Correct the malformed line in the release checklist.

#### Exit gate

> Workflow contract tests prove the complete artifact identity chain without using
> secrets, physical devices, or destructive external actions.

### A5 🤖 — Add automated parity and regression gates

**Objective:** Prevent Desktop/Quest residue and unsupported functionality from
silently returning.

#### Deliverables

- [ ] Create a machine-readable capability matrix for both products.
- [ ] Map every retained app, setting, menu, and runtime boundary to tests.
- [ ] Add Phone emulator tests for launcher, deep link, IME, Back, and lifecycle.
- [ ] Add Phone route tests for every retained tablet app.
- [ ] Add Pico Settings and menu snapshots/contracts.
- [ ] Add a test that rejects production crash/developer actions.
- [ ] Add Pico cache-upgrade and stale-asset tests.
- [ ] Integrate the preserved local native-coverage commits where still applicable.
- [ ] Clearly separate source-contract, emulator, and physical-device evidence in
  reports.

#### Exit gate

> A new Desktop option, menu, script, or dependency cannot become part of either
> mobile product without an explicit capability and test update.

### A6 🤖 — Reduce package and repository footprint

**Objective:** Lower APK size, attack surface, dependency cost, and review noise.

#### Android Phone

- [ ] Convert remaining script packaging to a positive allowlist.
- [ ] Audit shared `resources.rcc` reachability.
- [ ] Exclude unused desktop/HMD QML where selectors and runtime allow it.
- [ ] Re-measure the APK and native closure after each trim.

#### Pico 4

- [ ] Stop packaging the full developer tree.
- [ ] Stop packaging community and tutorial trees without product consumers.
- [ ] Remove unused Qt Contacts, DocGallery, Organizer, Feedback, and Versit
  libraries after dependency verification.
- [ ] Audit legacy Quest resources and selectors.
- [ ] Establish an APK size budget.

#### Repository hygiene

- [ ] Deduplicate repeated serverless-world fixtures.
- [ ] Replace giant chronological nightly documents with compact status reports and
  CI artifacts.
- [ ] Keep immutable raw test evidence outside product-source diffs where possible.

#### Exit gate

> Both APKs have documented budgets, every packaged component has a consumer, and
> status documentation remains reviewable.

---

## Personal choices and hardware milestones

These milestones need either a quick choice by the maintainer or time with real
hardware. They are not external approvals. Choose the smallest scope that sounds
fun and useful now; everything else can remain in Later or Maybe.

### B0 👤 — Choose the next useful outcomes

This is a personal scope exercise, not a permanent product contract. Revisit it
whenever priorities or available hardware change.

#### Android Phone

- [ ] Explore/social client only, or creator client as well?
- [ ] Would touch-owned Create add more value now than polishing Explore/social use?
- [ ] Is portrait orientation required?
- [ ] Is the sustained target 30 FPS, 60 FPS, or device-tiered?
- [ ] Are snapshots required, and which Android storage flow should own them?
- [ ] May More/Community download or install third-party scripts?
- [ ] Is an external avatar marketplace allowed?
- [ ] Keep diagnostics local, or deliberately opt into a privacy-respecting crash flow?
- [ ] F-Droid, Play, direct download, or multiple channels?

#### Pico 4

- [ ] Must Overte generate 72 new FPS, or is a measured reprojection target allowed?
- [ ] Which sustained temperature and battery limits are acceptable?
- [ ] Is WebChannel/EventBridge required for release?
- [ ] Which origins may call native/entity APIs?
- [ ] Which external controllers or trackers are worth personal experiment time?
- [ ] Are mirror, secondary camera, and full Create import mandatory?
- [ ] Consumer Store, Business Store, direct APK, or multiple channels?

#### Exit gate

> Each client has a one-page **Now / Later / Maybe / Not planned** list. “Now” stays
> small enough for one person to finish and test.

### S1 👤 — Make builds easy to share with testers

This is intentionally lightweight. It is enough to hand a known APK to a willing
tester and understand which source produced it.

- [ ] Produce clearly named Phone and Pico APKs from a recorded commit.
- [ ] Document the Android version, ABI, install command, and known limitations.
- [ ] Include “unofficial fork” and “not supported by the Overte team” in the build
  description and About/help surface where practical.
- [ ] Keep a tiny feedback template: device, OS, build SHA, steps, expected, actual.
- [ ] Never put signing keys or device credentials into the repository.
- [ ] Prefer local/debug or disposable test signing until a real distribution channel
  is worth the maintenance cost.

#### Optional automation

- [ ] Upload CI artifacts when this saves time compared with local builds.
- [ ] Add checksums and a short changelog for externally shared APKs.
- [ ] Use immutable tags only when calling a build a versioned public release.

#### Exit gate

> Another person can install the intended APK, identify its exact source revision,
> understand that it is unofficial, and return a useful bug report.

### H1 📱 — Android Phone hardware acceptance

#### Suggested coverage over time

Do not buy a device matrix just to satisfy this table. Start with available hardware,
then use volunteer reports to broaden coverage when possible.

| Dimension | Useful eventual coverage |
|---|---|
| GPU | One Adreno and one Mali device |
| Android | One API 26–29 and one API 30+ device |
| Display | Flat plus notch/hole-punch/rounded or asymmetric display |
| Network | Wi-Fi, mobile data, transition, loss, and reconnect |
| Session | Cold start, background/foreground, process recreation, 30–60 minute soak |

#### Core journeys

- [ ] Clean install and cold launch.
- [ ] Microphone allow and deny.
- [ ] Account login success, invalid credentials, cancellation, and logout.
- [ ] Domain login.
- [ ] IME resize, focus, gesture Back, and physical Back.
- [ ] Deep links before and after native runtime readiness.
- [ ] Audio input/output, mute, routing, and levels.
- [ ] Tablet open/home/close cycles for every retained application.
- [ ] No touch-through from tablet into world controls.
- [ ] People, Places, Avatar, Shield, and Emote success/error paths.
- [ ] Network transition and reconnect.
- [ ] Cutout, safe inset, DPI, and system-bar behavior.
- [ ] 30–60 minute populated-domain thermal/battery/audio/network soak.

#### Exit gate

> The core journey is enjoyable on available hardware, with no known critical UI,
> lifecycle, audio, networking, or rendering defect. Cross-GPU evidence is a bonus
> gained through volunteer testing, not a prerequisite for continued development.

### H2 🥽 — Pico correctness acceptance

#### OpenXR and input

- [ ] Both controllers and both hands.
- [ ] Trigger, grip, and sticks across tracking loss and recovery.
- [ ] Suspend/resume with controls held.
- [ ] Immediate neutral state and safe release.
- [ ] No stale click, grab, locomotion, scroll, or haptic state.

#### Interaction and Create

- [ ] Near/Far Grab with both hands.
- [ ] Rapid target changes.
- [ ] Off-hand rotation.
- [ ] Local and domain-hosted entities.
- [ ] Entity List and import.
- [ ] Mirror and secondary camera if retained.
- [ ] Long editing session.

#### Web entities

- [ ] Opaque and transparent pages.
- [ ] Transparent-centre content.
- [ ] Hover, click, drag, scroll, and pressed-target loss.
- [ ] Repeated resize, navigation, and destruction.
- [ ] Multiple WebView isolation.
- [ ] JNI/WebView log review.

#### Audio and lifecycle

- [ ] Rapid source switching and restart isolation.
- [ ] Fixed-phrase speech quality.
- [ ] AEC and echo evaluation.
- [ ] Sustained capture under automatic fan control.
- [ ] Activity background/resume and world reconnect.

#### Exit gate

> All mandatory XR, interaction, Create, Web, audio, and lifecycle journeys pass
> without stale state, crash, or unrecoverable degradation.

### H3 🥽 — Pico performance and thermal gate

**This is the highest-value Pico quality milestone:** poor frame pacing or thermal
cutoffs directly prevent enjoyable sessions, even for a personal build.

#### Test scenes

- [ ] Current live Hub baseline.
- [ ] Controlled moving-avatar population.
- [ ] Independent mixer-fed moving avatars.
- [ ] Mirror-heavy or secondary-camera scene.
- [ ] Create editing workload.
- [ ] Active Web entity workload if Web is in release scope.

#### Measurements

- [ ] Application-generated frame rate.
- [ ] Compositor presents and reprojection behavior.
- [ ] Frame pacing and dropped/new frames.
- [ ] Per-thread CPU and blocking hotspots.
- [ ] GPU frame time and clock.
- [ ] Controller-to-object and ray latency.
- [ ] CPU, GPU, skin, and battery temperature.
- [ ] Battery drain and fan behavior.
- [ ] 30–60 minute automatic-fan stability.

#### Optimization loop

```mermaid
flowchart LR
    M["🥽 Measure on hardware"] --> P["🤖 Profile and isolate CPU cost"]
    P --> C["🤖 Implement bounded change"]
    C --> T["🤖 Run device-free regressions"]
    T --> V["🥽 Repeat identical hardware A/B"]
    V -->|Target not met| P
    V -->|Target met| G["✅ Performance gate"]
```

#### Exit gate

> The personally chosen native-frame or reprojection target is sustained for 30–60 minutes,
> interaction latency is acceptable, and no thermal safety cutoff or progressive
> throttling occurs under automatic fan control.

### R1 🔐📱 — Optional Android Phone publishing

Skip this milestone until direct test APKs are useful and maintaining a public
distribution channel sounds worthwhile.

#### Deliverables

- [ ] All autonomous milestones complete.
- [ ] B0 scope chosen and S1 sharing flow proven.
- [ ] H1 hardware acceptance complete.
- [ ] Immutable release tag and monotonic version code.
- [ ] Store-neutral reproducibility candidate generated.
- [ ] Actual channel artifact signed with a securely retained key.
- [ ] Exact signed artifact passes package, 16 KiB, digest, signer, and device gates.
- [ ] F-Droid recipe or other selected distribution flow reviewed.
- [ ] A simple rollback/fix-forward and key-backup procedure exists.

#### Exit gate

> The exact bytes intended for users are signed, traceable to the reviewed source,
> hardware-tested, clearly unofficial, and distributed through a deliberately chosen
> channel that remains manageable for one maintainer.

### R2 🔐🥽 — Optional Pico 4 publishing

Skip this milestone until sideloaded builds are stable enough that store or wider
distribution would genuinely help users.

#### Deliverables

- [ ] All autonomous milestones complete.
- [ ] B0 scope chosen and S1 sharing flow proven.
- [ ] H2 and H3 hardware gates complete.
- [ ] Trusted build succeeds from a clean checkout.
- [ ] Signed RC workflow succeeds from an immutable tag.
- [ ] Draft release metadata, SBOM, checksums, and provenance reviewed.
- [ ] Exact signed APK passes protected device acceptance.
- [ ] PICO portal confirms package ownership and current APK-size limit.
- [ ] If using a store, its regions, OS versions, controller declarations,
  permissions, UGC, age rating, privacy, licenses, and signing rules are understood.

#### Exit gate

> A signed Pico artifact is reproducible, hardware-tested, clearly unofficial, and
> compatible with the chosen distribution path. A direct sideload remains a valid
> endpoint for this hobby project.

---

## Optional feature milestone

### F1 🤖 after B0 — Implement chosen useful parity

Start an item only after choosing it for “Now.” Useful outcomes matter more than
matching every Desktop feature, while final confidence still comes from H1/H2.

#### Candidate Phone features

| Feature | Required design boundary |
|---|---|
| Touch-owned Create | Screen-space selection, editing, dialogs, import, undo, and lifecycle; do not wrap Desktop Create wholesale |
| Snapshots | Android storage/media APIs; no desktop directory picker |
| More/Community | Provenance, signatures, origin policy, sandbox, revocation, and user consent |
| Avatar marketplace | Approved remote-content and browser boundary |
| Portrait | WindowInsets transport, responsive layouts, world controls, IME, and rotation lifecycle |

#### Candidate Pico features

| Feature | Required design boundary |
|---|---|
| WebChannel/EventBridge | Reviewed origin/frame policy and narrow native API protocol |
| Full Create import | File/content provider, archive safety, lifecycle, and controller UX |
| External trackers/controllers | Explicit support matrix and fail-closed input state |
| Mirror/secondary camera | Measured performance budget and comfort review |

#### Exit gate

> Every chosen feature has a platform-owned UX, explicit security boundary,
> automated contracts, and the appropriate Phone or Pico hardware acceptance.

## Suggested execution waves

| Wave | Milestones | Outcome |
|---|---|---|
| 0 — Stabilize | A0, B0 kickoff | Work preserved; a small personal scope is visible |
| 1 — Converge | A1 | One mobile source line |
| 2 — Harden | A2, A3, A4 | Safe shared core, clean UI, coherent workflows |
| 3 — Prove | A5, A6, S1 | Automated checks, smaller packages, shareable APKs |
| 4 — Validate | H1, H2 | Phone and Pico correctness evidence |
| 5 — Optimize | H3 | Pico becomes comfortable enough for longer sessions |
| 6 — Add value | F1 where chosen | Platform-appropriate useful parity |
| 7 — Publish, optionally | R1, R2 | Signed and traceable public builds if worthwhile |

## Progress dashboard

### Shared gates

- [ ] One authoritative integration branch.
- [ ] Both device-free suites pass from the same commit.
- [ ] Shared Android cache and lifecycle foundations.
- [ ] Capability-based Settings and Menu policies.
- [ ] No production Developer/Crash actions.
- [ ] Workflow artifact identity is coherent and tested.
- [ ] Package footprint and dependency inventory reviewed.

### Android Phone gates

- [ ] Trusted build registered and passing.
- [ ] Installable emulator/instrumentation lane passing.
- [ ] Signed-channel artifact acceptance passing.
- [ ] Adreno and Mali hardware matrix passing.
- [ ] 30–60 minute interactive soak passing.
- [ ] A shareable APK and installation notes exist.

### Pico 4 gates

- [ ] Trusted build passing.
- [ ] Signed RC draft workflow passing.
- [ ] Protected device acceptance passing.
- [ ] Both-hand/tracking-loss/Create/Web/audio correctness passing.
- [ ] Sustained performance target passing.
- [ ] Automatic-fan thermal soak passing.
- [ ] A shareable APK and installation notes exist.

## Three sensible finish lines

This project does not need one heavyweight definition of done. Use the finish line
that matches the current goal:

### 1. Works for me

- The core journey works on the maintainer's available hardware.
- No known crash, dangerous control, overheating loop, or data-loss issue blocks a
  normal session.
- Known limitations are written down.

### 2. Shareable community build

- Another person can install a revision-identifiable APK and complete the core
  journey.
- The build is clearly labeled as an unofficial fork with no official Overte support.
- Feedback is reproducible enough to guide the next hobby session.

### 3. Distribution-ready, only if desired

If wider publishing becomes worthwhile, then apply the stricter checks below:

1. **Source:** The exact source is immutable, reviewed, and built from the shared
   integration line.
2. **Build:** Dependencies, package contents, ABI, version, and provenance are
   reproducible and verified.
3. **Security:** Platform UI is fail closed, dangerous actions are unavailable, and
   remote-content boundaries are explicit.
4. **Correctness:** Automated, emulator, and physical-device gates cover the product's
   mandatory journeys.
5. **Performance:** Sustained hardware targets pass without unacceptable latency,
   thermal cutoff, or battery behavior.
6. **Artifact:** The exact signed bytes intended for users pass final acceptance.
7. **Operations:** Signing, rollback/fix-forward, key recovery, privacy, and the
   chosen distribution process are documented at a maintainable level.

A green device-free CI run is useful evidence, not a substitute for trying the build.
Conversely, a fun and stable sideloaded build can be a success without satisfying
store-grade process requirements.
