# Device and desktop E2E test strategy

## Objective

Write observable Overte behavior once and implement only transport and input
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

The baseline runs in one application session after the initial controlled
launch. Shared modules own expectations. Product adapters own target discovery,
process lifecycle, launch arguments, UI and input translation, probe transport,
diagnostics, and cleanup. CI orchestration owns neither behavior nor platform
logic.

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
  positive and negative tests. Product adapters intentionally omit
  `navigation.enter-domain` until separately activated and accepted.

Concrete transports, package formats, signing rules, system services, device
selectors, accessibility mappings, and toolchain locks belong to product
branches. A transport is promoted to a parent branch only when every child of
that parent can use the same implementation without importing a child backend.

## Pass criteria

- Scene: the requested controlled scene is observed, all fixture markers
  exist, and the nearby entity count is stable for consecutive probe samples.
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
- Semantic tablet: the expected ready screen and stable visible semantic IDs
  are adapter observations, while required and forbidden features come from a
  separately validated product policy. Negative assertions run only after a
  stable ready screen. See [`TABLET_E2E.md`](TABLET_E2E.md).
- Sound: fixture request telemetry, decoded `SoundObject` readiness, two fresh
  active injector samples, regular finish or stop, and stable process identity
  are all required. This is an in-client proof, not a physical-output proof;
  see [`SOUND_E2E.md`](SOUND_E2E.md).
- Launch and soak: process identity remains stable and foreground state is
  observed throughout the selected sequence.
- Domain entry: the probe reports the fixture's exact UUID and host, leaves
  serverless mode, observes the complete assignment-owned marker set for
  consecutive stable samples, and retains foreground/process identity.

Every module retains its last, before, and after probe snapshots. Target
adapters may add redacted screenshots, accessibility trees, or private device
logs. Raw user content, visited production locations, account identifiers,
and transport selectors must not be archived. Every snapshot includes platform
and build identity so an archived result identifies the tested binary.

## Failure classification

- **Passed:** the expected product behavior was observed.
- **Skipped:** the target truthfully lacks an optional declared capability.
- **Assertion failure:** Overte ran but did not exhibit required behavior.
- **Infrastructure error:** the device, automation transport, fixture, or
  probe was unavailable or invalid.

This distinction prevents an offline target from being counted as a product
regression and prevents an unsupported operation from being counted as a pass.
CI acceptance uses `--require-complete`, so the baseline cannot silently skip a
required capability.

## Hardware acceptance gates

Repository tests can prove contracts, protocol translation, failure handling,
redaction, and reporting without hardware. Before a target receives a regular
schedule, record evidence for:

- discovery of the intended physical or interactive target;
- idempotent cleanup before and after failures;
- fixture reachability from the target;
- an audited accessibility tree when native selectors are used;
- every advertised input effect observed through the probe;
- diagnostics that contain no private selector or credential leakage;
- repeatability of at least 20 short `e2e-core` runs;
- recovery after transport loss, automation restart, application crash, and
  timeout; and
- required operating-system permissions in the same context as the CI agent.

Long soaks begin only after the short baseline is reliable. They do not
compensate for a failing or incomplete core sequence.
