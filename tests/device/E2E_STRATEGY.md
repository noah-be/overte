# Physical-device E2E test strategy

## Objective

Write observable Overte behavior once and implement only transport/input
operations per target. The initial behavior contract is deliberately small:

1. start Overte once;
2. load a controlled local scene;
3. observe a valid spawn above the ground;
4. perform look input and observe an orientation change;
5. perform movement input and observe an avatar-position change;
6. open the system tablet and observe its state;
7. close the system tablet and observe its state;
8. enter a controlled domain and receive its assignment-owned
   content without a process restart.
9. evaluate process identity, probe state, errors, and artifacts; and
10. clean up the application session and target transport.

The shared modules own expectations. Adapters own device discovery, process
lifecycle, UI/input translation, probe transport, and cleanup. Jenkins owns
neither behavior nor platform logic.

## Implementation sequence and status

1. **Portable runner and capability schema — implemented.** The runner works
   on POSIX and Windows, launches Python commands portably, distinguishes
   assertion/skip/infrastructure outcomes, and validates the versioned registry.
2. **Controlled local/network fixture — implemented.** The four-entity
   serverless scene is dependency-free, self-validating, and served by the
   Python standard library with a health endpoint.
3. **Overte probe and `OverteSession` — implemented.** One Interface test
   script emits the observable state used by every platform.
4. **Phone/Pico ADB behind adapter operations — implemented.** Existing
   release scripts remain stronger packaging/provenance gates; the universal
   adapters expose their runtime primitives.
5. **Common scene/look/move/tablet modules — implemented.** A deterministic
   state-machine adapter executes the entire suite in hardware-free CI.
6. **Appium transport — Android implemented; iOS software contract
   implemented, signed artifact gated.** W3C transport, source capture and
   audited-label checks are tested against a fake Appium server. Android has a
   debug-only controlled launcher. iOS now has a fail-closed test-build
   contract, runtime plist attestation, controlled relaunch arguments, and
   Documents probe transfer. This checkout has no maintained iOS application
   target, so producing/signing that artifact and auditing the real QML tree
   remain hardware/platform gates.
7. **Local Jenkins device lab — implemented.** Start with `smoke`, add
   `e2e-core` on an input-capable profile, and enable lifecycle/thermal soaks
   only after target pass rates are stable.
8. **Controlled domain-entry contract — implemented, adapter rollout gated.**
   An ephemeral local domain/assignment fixture, exact identity/content checks,
   and hardware-free positive and negative tests are in place. Android and
   Appium adapters expose only their target-owned controlled command paths and
   remain disabled until separately activated and accepted.

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
  four fixture markers exist and the nearby entity count is stable for
  consecutive probe samples.
- Look: the camera's observed Euler-angle delta crosses a configurable minimum.
- Move: the avatar baseline is stable before input, then displacement crosses a
  configurable minimum in the controlled collision scene.
- Spawn: the avatar position is finite and above the fixture ground within the
  declared tolerance.
- Jump: a stable grounded baseline precedes exactly one `input.jump`; the probe
  then observes configurable height gain with `inAir=true` and `flying=false`,
  followed by `inAir=false` near the baseline height.
- Fly: a stable grounded baseline reports `flyingEnabled=true`; bounded
  `input.fly` then produces configurable height gain with both `inAir=true`
  and `flying=true`.
- Tablet: both open and closed state transitions are observed in Interface,
  not inferred from a successful click, key, or gesture command.
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
