# Physical-device E2E test strategy

## Objective

Write observable Overte behavior once and implement only transport/input
operations per target. The initial behavior contract is deliberately small:

1. start Overte once;
2. load a controlled local scene;
3. observe a valid spawn above the ground;
4. perform signed look input in every direction;
5. perform body-relative movement in every direction and reject stuck input;
6. collide with the controlled wall, jump and fly;
7. open and close the system tablet and reject world-input leakage;
8. reload the scene and optionally stop/relaunch the application;
9. enter a controlled domain and receive its assignment-owned
   content without a process restart.
10. evaluate process identity, probe state, errors, and artifacts; and
11. clean up the application session and target transport.

The shared modules own expectations. Adapters own device discovery, process
lifecycle, UI/input translation, probe transport, and cleanup. Jenkins owns
neither behavior nor platform logic.

## Shared implementation

- The portable runner works on POSIX and Windows, launches adapter commands
  portably, validates the versioned registry, and distinguishes assertion,
  skip, and infrastructure outcomes.
- The controlled five-entity serverless scene is dependency-free,
  self-validating, and served by the Python standard library.
- One schema-v2 Interface probe emits monotonic, strict observable state used
  by every platform while retaining domain, asset, and sound evidence.
- The common scene, look, movement, tablet, accessibility, launch, and soak
  modules consume only versioned adapter capabilities.
- A deterministic state-machine adapter executes the full baseline in
  hardware-free CI.
- The controlled domain-entry contract includes an ephemeral local
  domain/assignment fixture, exact identity/content checks, and hardware-free
  positive and negative tests. Android adapters add their target-owned
  controlled command paths only after separate activation and acceptance.

Concrete transports, package formats, signing rules, system services, device
selectors, accessibility mappings, and toolchain locks belong to product
branches. A transport is promoted to a parent branch only when every child of
that parent can use it without importing a child backend.

## Target matrix

| Target | Automation owner | Common verification | Host requirement |
|---|---|---|---|
| Android Phone | Appium UiAutomator2; ADB lifecycle | Overte probe | Linux/macOS/Windows with USB access |
| Pico/Android VR | ADB lifecycle; test-only OpenXR API-layer prototype | Overte probe | Host with authorized ADB |
| iPhone/iPad | Appium XCUITest + RemoteXPC | Lifecycle and test-build/probe contract; physical behavior after signed artifact acceptance | Protected macOS build/sign producer; Fedora physical-device agent on iOS 18+ |

Pico/Quest head pose and tracked-controller input cannot honestly be emulated
by ordinary ADB. [`openxr_input/`](openxr_input/) now defines and validates a
bounded, nonce-protected, test-only OpenXR API-layer protocol, but the adapter
still must not advertise `input.look`, `input.move`, or tablet input until that
layer is packaged in the E2E debug APK and accepted on physical hardware.
Capability-based skipping keeps that gate visible instead of manufacturing a
false pass.

One physical Android phone can therefore have two Jenkins jobs without
duplicating scenarios: Appium owns core input/accessibility, while its ADB
process observer supplies identity and telemetry; a pure ADB profile remains
useful for fast smoke and soak jobs. Both jobs lock the same Jenkins device
resource.

## Pass criteria

- Scene: for a network fixture the requested URL is observed; for an embedded
  Android fixture the adapter declares marker verification. In both cases all
  five fixture markers exist and the nearby entity count is stable for
  consecutive probe samples.
- Spawn: the avatar position is finite and above the fixture ground within the
  declared tolerance.
- Look: each signed camera-orientation delta crosses a configurable minimum in
  the requested left, right, up, or down direction.
- Move: the avatar baseline is neutral before input, then displacement crosses
  a configurable minimum along the requested body-yaw-relative axis.
- Neutral input: velocity, positional drift, and view drift remain below their
  configured bounds for consecutive fresh samples.
- Collision: the avatar approaches the repository-owned wall, cannot pass its
  near face, and does not stop implausibly far away.
- Jump: a stable grounded baseline precedes exactly one `input.jump`; the probe
  then observes configurable height gain with `inAir=true` and `flying=false`,
  followed by `inAir=false` near the baseline height.
- Fly: a stable grounded baseline reports `flyingEnabled=true`; bounded
  `input.fly` then produces configurable height gain with both `inAir=true`
  and `flying=true`.
- Tablet: both open and closed state transitions are observed in Interface,
  not inferred from a successful click, key, or gesture command.
- Tablet isolation: movement input while the tablet owns focus produces no
  observable world displacement or velocity.
- Recovery: scene reload restores the controlled fixture; application restart
  proves stop state, relaunch, a new identity, foreground state, and stability.
- Sound: fixture request telemetry, decoded `SoundObject` readiness, two fresh
  active injector samples, regular finish or stop, and stable process identity
  are all required. This is an in-client proof, not a physical-output proof;
  see [`SOUND_E2E.md`](SOUND_E2E.md).
- Launch and soak: process identity remains stable and foreground state is
  observed throughout the selected sequence.
- Domain entry: the probe reports the fixture's exact UUID and host, leaves
  serverless mode, observes the complete assignment-owned marker set for
  consecutive stable samples, and retains foreground/process identity.

Every module retains its last/before/after probe snapshots. Target adapters can
add screenshots, native accessibility XML, Appium logs, or private device logs.
Raw user content, visited production locations, account identifiers, and
transport selectors must not be archived.
Every probe snapshot includes `About.platform`, build version, and build date so
an archived result identifies the Overte binary that produced the evidence.

## Failure classification

- **Passed:** expectation observed; module exit `0`.
- **Skipped:** target truthfully lacks the declared capability; runner result
  `skipped`, not passed.
- **Assertion failure:** Overte ran but did not exhibit the required behavior.
- **Infrastructure error:** disconnected device, Appium/ADB failure, stale
  probe, or automation transport error; module
  exit `75`, JUnit `<error>`.

This distinction prevents an offline phone from being counted as a product
regression and prevents an unsupported operation from being counted as success.

## Open-source tooling boundary

The harness and probe are Apache-2.0 with Overte. Jenkins and its Lockable
Resources/JUnit plugins, Appium, UiAutomator2, Appium XCUITest driver, ADB, and
Java runtimes all have open-source implementations.

iOS has an unavoidable producer exception: builds and signatures require
Apple's proprietary Xcode toolchain, device signing, and provisioning. The
runtime controller does not have to be macOS. On physical iOS 18+ targets,
Fedora runs the open-source Appium/RemoteXPC stack with an exact, prebuilt and
signed WebDriverAgent. Therefore iOS cannot satisfy a literal end-to-end “only
open-source software” constraint, but all test orchestration, transport,
monitoring, assertions, and reporting remain on the Fedora lab.

## Hardware acceptance gates

The repository can prove contracts, failure handling, protocol translation and
reporting without hardware. It cannot autonomously grant OS permissions,
unlock devices, accept trust prompts, sign WDA, or demonstrate a real sensor/UI
effect. Before a target receives a Jenkins schedule, record evidence for:

- discovery and idempotent cleanup on the intended physical target;
- a real Accessibility tree where Appium is used;
- fixture reachability from the device network;
- all advertised operation effects observed through the probe;
- screenshot/log collection with no private selector leakage where the target
  advertises capture;
- repeatability of at least 20 short `e2e-core` runs;
- recovery after cable removal, Appium restart, application crash, and timeout;
- OS-specific permissions in the same login context as the Jenkins agent.

Long soaks are enabled only after those gates pass. They do not compensate for
an unreliable short suite.

## Primary tool references

- [Appium UiAutomator2 setup](https://appium.io/docs/en/latest/quickstart/uiauto2-driver/)
- [Appium XCUITest physical-device preparation](https://appium.github.io/appium-xcuitest-driver/latest/getting-started/device-setup/)
- [Jenkins Lockable Resources Pipeline step](https://www.jenkins.io/doc/pipeline/steps/lockable-resources/)
- [Jenkins credential handling](https://www.jenkins.io/doc/book/using/using-credentials/)
