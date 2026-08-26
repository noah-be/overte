# Device and desktop E2E test strategy

## Objective

Write observable Overte behavior once and implement only transport and input
operations per target. The V1 baseline is:

1. start Overte once;
2. load a controlled local scene;
3. observe a valid spawn above the ground;
4. look left, right, up, and down with the matching signed rotation;
5. move forward, backward, left, and right relative to avatar body yaw;
6. prove that bounded input returns to a neutral state;
7. collide with the deterministic wall without passing through it;
8. jump with non-flying ascent and a verified landing;
9. open and close the tablet and prove tablet input cannot move the avatar;
10. fly upward with active flight state and measured height gain;
11. reload the controlled scene and verify its restored state;
12. stop and restart Overte with a new stable foreground process; and
13. evaluate evidence and clean up the target transport.

The baseline reuses one application session until the final explicit restart
check. Shared modules own expectations. Product adapters own target discovery,
process lifecycle, launch arguments, UI and input translation, probe transport,
diagnostics, and cleanup. CI orchestration owns neither behavior nor platform
logic.

## Shared implementation

- The portable runner works on POSIX and Windows, launches adapter commands
  portably, validates the versioned registry, and distinguishes assertion,
  skip, and infrastructure outcomes.
- The controlled five-entity serverless scene is dependency-free,
  self-validating, and served by the Python standard library.
- One Interface probe emits the observable state used by every platform.
- The common V1 behavior modules consume only versioned semantic adapter
  capabilities. The catalog contains no platform events, controller names,
  touch coordinates, package identifiers, or automation backend details.
- A deterministic state-machine adapter executes the full baseline in
  hardware-free CI.

Concrete transports, package formats, signing rules, system services, device
selectors, accessibility mappings, and toolchain locks belong to product
branches. A transport is promoted to a parent branch only when every child of
that parent can use the same implementation without importing a child backend.

## Pass criteria

- Scene: the requested controlled scene is observed, all fixture markers
  exist, and the nearby entity count is stable for consecutive probe samples.
- Spawn: the avatar position is finite and above the fixture ground within the
  declared tolerance.
- Look: the camera's signed yaw or pitch delta matches the requested direction
  and crosses a configurable minimum.
- Move: the avatar baseline is neutral before input, then the signed projection
  of planar displacement relative to observed body yaw matches the requested
  direction and crosses a configurable minimum.
- Input neutral: consecutive fresh samples stay below configurable avatar
  speed, position drift, and view drift thresholds.
- Collision: the avatar approaches the declared wall, reaches its near face,
  and never appears on the far side.
- Jump: a stable grounded baseline precedes exactly one `input.jump`; the probe
  then observes configurable height gain with `inAir=true` and `flying=false`,
  followed by `inAir=false` near the baseline height.
- Fly: a stable grounded baseline reports `flyingEnabled=true`; bounded
  `input.fly` then produces configurable height gain with both `inAir=true`
  and `flying=true`.
- Tablet: both open and closed state transitions are observed in Interface,
  and equivalent movement input while open produces neither locomotion nor
  non-neutral velocity.
- Scene reload: all five fixture markers, floor state, wall geometry, entity
  count, and spawn validation return after a new load request.
- App restart: stop is observed before launch; the relaunched foreground
  process has a non-empty identity different from the stopped process.
- Launch and soak: process identity remains stable and foreground state is
  observed throughout the selected sequence.

Every observation is newer than the preceding `sampleSequence`; cached probe
evidence is an infrastructure error. Every module retains its last, before,
and after probe snapshots. Target
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
- all `e2e-core-v1` capabilities advertised without skips and every input
  effect observed through the probe;
- diagnostics that contain no private selector or credential leakage;
- repeatability of at least 20 short `e2e-core-v1` runs;
- recovery after transport loss, automation restart, application crash, and
  timeout; and
- required operating-system permissions in the same context as the CI agent.

Only then should Jenkins run that target with `--require-complete`. Long soaks
begin only after the short baseline is reliable. They do not compensate for a
failing or incomplete core sequence.
