# Overte device E2E harness

The lifecycle policy, common CI flow, evidence contracts and portable suite
frontier are documented in
[`CROSS_PLATFORM_OPERATIONS.md`](CROSS_PLATFORM_OPERATIONS.md).

This directory contains the platform-neutral orchestration layer for device
and desktop E2E tests. Scenarios contain no operating-system, packaging, or
transport details. Product branches provide adapters that translate the
versioned capability contract into their native automation tools.

## Architecture

```text
catalog module -> OverteSession -> adapter operation -> target automation
                                      |
                                      +-> in-client Overte probe

fixture server -> controlled serverless scene
domain fixture -> ephemeral domain + assignment-owned marker scene
runner         -> shared target lock, timeout, cleanup, JSON, JUnit, private artifacts
matrix         -> selector-free cross-platform acceptance result
```

The runner reserves exactly one target for a complete run, applies module
timeouts to process groups, always calls idempotent cleanup, redacts private
selectors, and stores diagnostics outside the source tree. Exit code `0`
passes, `77` skips a missing optional capability, `75` reports device-lab
infrastructure failure, and other non-zero codes report an application
assertion failure.

Reservations are keyed by the private target selector rather than the adapter
ID, so two different automation backends cannot use the same device at once.
An adapter may return a private `reservationKey` when multiple backends use
different selectors for one physical device. Neither value is persisted.
`OVERTE_DEVICE_LOCK_TIMEOUT_SECONDS` bounds queueing (default 600 seconds).

## Portable suites

- `portable-smoke`: the canonical one-session route used unchanged on
  Android, iOS, Pico, Linux, macOS, and Windows: launch, controlled scene,
  signed look, body-relative movement, tablet open/close, then unconditional
  cleanup. Platform routing and the install/evidence baseline are declared in
  [`platform-adapters.json`](platform-adapters.json).
- `smoke`: stable process launch and foreground state.
- `asset-smoke`: one launch followed by controlled local texture delivery,
  ready resource state, uniquely tagged Image-entity use, and stable
  process/foreground evidence. Test logic is implemented; product-adapter
  activation remains pending. See [`ASSET_LOAD_E2E.md`](ASSET_LOAD_E2E.md).
- `sound-smoke`: controlled WAV request, decode readiness, and observable
  in-client injector lifecycle; see [`SOUND_E2E.md`](SOUND_E2E.md).
- `e2e-core`: launch, controlled scene and grounded spawn, signed look in four
  directions, body-relative movement in four directions, neutral input,
  collision, jump, flight, tablet transitions and input isolation, and scene
  reload.
- `e2e-recovery`: controlled scene reload followed by a stop/relaunch cycle
  that must produce a new stable process identity.
- `tablet-e2e`: one-process semantic tablet navigation and ready-state
  observation against an external product policy; see
  [`TABLET_E2E.md`](TABLET_E2E.md).
- `domain-smoke`: launch, enter an ephemeral controlled domain, and verify its
  exact identity and assignment-owned content without restarting Interface.
- `domain-recovery`: enter the controlled domain, leave it for the serverless
  fixture, and re-enter the same domain with stable content and process
  identity.
- `interaction-smoke`: load the controlled scene and prove that one native
  mouse click, touch action, or controller trigger produces exactly one press
  event on its interaction target; see
  [`INTERACTION_E2E.md`](INTERACTION_E2E.md).
- `text-input-smoke`: edit and submit fixed Unicode text through the native
  target input path, dismiss focus/keyboard state, and reject world-input
  leakage.
- `scripted-entity-smoke`: prove controlled client entity script loading,
  execution, event delivery, and independent entity mutation.
- `multi-user-smoke`: observe deterministic peer movement, departure, and the
  same peer session after reconnecting to the controlled domain.
- `network-fault-recovery`: stop and restore only the ephemeral domain stack,
  observe disconnect, and require automatic same-process reconnection. These
  gates are specified in
  [`PORTABLE_EXTENDED_E2E.md`](PORTABLE_EXTENDED_E2E.md).
- `audio-controls`: toggle and restore native microphone mute with independent
  in-client state.
- `settings-persistence`: change one safe setting, restart, verify, restore,
  and verify restoration after another restart.
- `lifecycle-under-load`: background and reactivate a ready scene with an open
  tablet while retaining process, content, UI state, and renderer progress.
- `render-health`: combine native GPU/surface/frame evidence with independently
  advancing render statistics and reject black or software frames.
- `vertical-locomotion`: one jump with observed ascent and landing, followed by
  bounded flight with observed active ascent. Adapters lacking either input
  capability skip only the corresponding module unless `--require-complete`
  is selected.
- `accessibility`: native-tree audit against explicitly configured stable UI
  accessibility identifiers.
- `stability`: idle process and foreground health, with strict battery,
  memory, and thermal samples when the adapter advertises telemetry.
- `lifecycle-stability`: repeated background and activation cycles with a
  stable process identity on targets that support lifecycle automation.

All behavioral modules use `OverteSession` and verify effects through fresh
schema-v2 `probe.snapshot` samples. A successful input command alone is never
enough to pass a behavior.

`domain-smoke` and `domain-recovery` are fully specified and hardware-free
tested. Advertisement by a concrete adapter remains a separate per-platform
acceptance step in its product branch.

## Adapter protocol

An adapter manifest uses schema version 1:

```json
{
  "schemaVersion": 1,
  "id": "mock-device",
  "command": ["adapter.py"]
}
```

Relative commands are resolved against the manifest directory. The executable
receives one command and writes exactly one JSON value:

```text
adapter discover
adapter describe --target TARGET
adapter invoke --target TARGET --operation OPERATION --arguments JSON
adapter cleanup --target TARGET
```

`discover` returns `selector`, `displayName`, `platform`, `physical`, and a
sorted `capabilities` list, plus an optional private `reservationKey`.
Selectors are private transport identifiers and must never appear in
descriptions or persisted output. Supported operation
names and results are versioned in [`capabilities.json`](capabilities.json).
Machine-readable catalog, adapter, probe, run, and matrix schemas are in
[`schemas/`](schemas/).

Every target promoted to the portable baseline must advertise installation,
launch, process monitoring, controlled scene, look, movement, tablet
open/close, screenshot, and video. Cleanup is the mandatory idempotent adapter
action rather than a scenario operation. Validate a provisioned target with
`verify_adapter.py --portable-baseline --require-target`; this also invokes
cleanup twice. A preinstalled-only iOS target may run behavioral development
smokes, but cannot be promoted because it deliberately cannot prove
`app.install`.

The common input and lifecycle contract is deliberately small:

- `input.jump` accepts `{}` and returns at least `{"performed": true}`.
- `input.fly` accepts only `{"durationSeconds": NUMBER}`, bounded from `0.1`
  through `10.0`, and returns at least `{"performed": true}`.
- `input.look` accepts bounded non-zero horizontal and vertical components;
  positive values mean right and up.
- `input.move` accepts one of `forward`, `backward`, `left`, or `right` and a
  duration from `0.1` through `10.0` seconds.
- `input.primary` accepts `{}` and performs one platform-native primary press
  and release aimed at the controlled interaction target. The probe, not the
  adapter result, proves delivery to the entity.
- `text.focus`, `text.type`, `text.snapshot`, and `text.dismiss` expose only a
  repository-owned test field. `text.type` carries bounded fixed Unicode text,
  editing, and submit intent; direct value assignment is not conforming.
- `probe.snapshot` accepts an optional positive `afterSampleSequence` cursor;
  the returned v2 sample must advance beyond it.
- `app.stop` accepts `{}` and confirms `{"stopped": true}`.

No shared module knows controller buttons, native events, or input routes.

The semantic tablet extension adds `tablet.snapshot` and `tablet.activate`.
Its version 1 taxonomy, exact request/response formats, policy separation and
product-adapter handoff are documented in [`TABLET_E2E.md`](TABLET_E2E.md).
The runner deliberately does not expose the selected policy path to adapter
processes.

[`adapters/mock/`](adapters/mock/) is a deterministic state machine that proves
every common scenario without hardware. Concrete adapters, private target
configuration examples, installation logic, and platform toolchains belong to
their product branches. Real target configuration must remain outside the
checkout; never commit device identifiers, account paths, signing data, or CI
credentials.

## Controlled fixture and probe

[`fixture/scene.json`](fixture/scene.json) contains six local primitive
entities, including a deterministic collision wall and scripted interaction
target, and no external assets.
Start an ephemeral localhost server with:

```bash
python3 tests/device/fixture/serve.py --ready-file /tmp/overte-fixture.json
```

For a device on the LAN, bind all interfaces and provide its reachable host
address:

```bash
python3 tests/device/fixture/serve.py \
  --bind 0.0.0.0 --public-host 192.0.2.10 --port 18080 \
  --ready-file /tmp/overte-fixture.json
```

The server exposes the repository-owned probe at `/overte_e2e_probe.js` and the
pinned texture plus per-request telemetry used by `asset-smoke`, together with
the deterministic sound described in [`SOUND_E2E.md`](SOUND_E2E.md). The
in-client [`probe/overte_e2e_probe.js`](probe/overte_e2e_probe.js) records
application focus, scene readiness and markers, collision geometry, avatar
position, velocity and body yaw, `inAir`, `flying`, `flyingEnabled`, camera
orientation, tablet state, controlled asset resource/entity evidence, sound
resource and injector state, world-interaction events, client entity-script
state, controlled peer replication, monotonic sample sequence, and build identity
through Interface's existing test-script result API. It records no audio
samples. Product adapters own the exact launch and result transport used to
load it. The fixture exposes a same-origin `/e2e-client-command.json` channel;
controlled adapters POST strict commands there and verify the exact response.
The probe accepts only versioned HTTP scene, domain navigation, controlled
local Image-entity, fixture sound-channel, and bounded allowlisted semantic
input-hold commands. The probe routes those holds through temporary Controller
actions, without requiring synthetic-key permissions or directly changing
avatar state. Every held input is released on its timer or probe shutdown. A
probe without the controlled HTTP route stops polling the channel.

The tablet observation combines `tabletShown` with the application-level
`HMD.showTablet` state because `tabletShown` is intentionally unused when a
desktop target presents the tablet in toolbar mode.
Semantic world-input routes remain neutral while that tablet state is active,
matching the focus boundary applied to physical desktop keyboard input; the
ContextMenu route remains available so the same bounded command can close it.

[`fixture/domain.py`](fixture/domain.py) owns the complementary ephemeral
domain-server and assignment-client stack, including a deterministic peer and
a loopback-only stop/start endpoint. The `domain-smoke` assertion waits
for the exact `/id` UUID, host, all repository-owned domain markers, stable
entity samples, foreground state, and unchanged process identity. See
[`fixture/DOMAIN.md`](fixture/DOMAIN.md) for the local run and environment
handoff.

## Running

List or run the common suite against the deterministic adapter:

```bash
python3 tests/device/run.py \
  --adapter-manifest tests/device/adapters/mock/adapter.json \
  --catalog tests/device/catalog.json --suite e2e-core --list

python3 tests/device/run.py \
  --adapter-manifest tests/device/adapters/mock/adapter.json \
  --catalog tests/device/catalog.json --suite vertical-locomotion \
  --output-dir /tmp/overte-device-run --require-complete

OVERTE_MOCK_TABLET_UI_PROFILE=flat python3 tests/device/run.py \
  --adapter-manifest tests/device/adapters/mock/adapter.json \
  --catalog tests/device/catalog.json --suite tablet-e2e \
  --tablet-policy tests/device/policies/mock-flat-touch.json \
  --allow-virtual --require-complete
```

Use `--target` only when discovery yields multiple targets. The value is never
persisted, but shell tracing must still be disabled around it in CI.

Verify the device-free implementation:

```bash
python3 -m unittest discover -s tests/device/self_tests -v
tests/device/qml/run-qml-tests.sh
python3 tests/device/fixture/serve.py --check
python3 tests/device/fixture/domain.py --check
python3 tests/device/run_control_plane_tests.py --profile quick \
  --junit /tmp/overte-device-control-plane.xml
```

Compile and execute a target-neutral plan. Scene-backed suites start and stop the
controlled HTTP fixture automatically; domain-backed suites additionally require
the two server executable paths:

```bash
python3 tests/device/execution_plan.py \
  --policy tests/device/acceptance-policy.json \
  --catalog tests/device/catalog.json \
  --profiles tests/device/execution-profiles.json \
  --platform mock --suite e2e-core \
  --fixture-provider auto --require-ready

python3 tests/device/pipeline.py \
  --adapter-manifest tests/device/adapters/mock/adapter.json \
  --catalog tests/device/catalog.json \
  --policy tests/device/acceptance-policy.json \
  --profiles tests/device/execution-profiles.json \
  --platform mock --suite e2e-core --allow-virtual \
  --output-dir /tmp/overte-device-pipeline
```

Every target adapter should also pass the reusable protocol verifier. The
optional cleanup check calls cleanup twice and verifies idempotency directly:

```bash
python3 tests/device/verify_adapter.py \
  --adapter-manifest path/to/adapter.json --require-target --check-cleanup
```

Every run writes `summary.json`, `junit.xml`, and a selector-free
`run-manifest.json`. Aggregate finished platform jobs into one enforceable
matrix without exposing result paths or device identifiers:

```bash
python3 tests/device/evaluate_matrix.py \
  --result /private/results/android-core \
  --result /private/results/ios-interaction \
  --require android:e2e-core \
  --require ios:interaction-smoke \
  --output-dir /tmp/overte-e2e-matrix
```

The evaluator returns `0` for a satisfied matrix, `1` for product assertion
failures, and `2` for infrastructure errors, invalid results, or missing
complete physical gates. Its JSON and JUnit outputs contain only ordinal run
IDs plus public adapter, platform, suite, duration, and status fields.

See [`E2E_STRATEGY.md`](E2E_STRATEGY.md) for the shared behavior contract,
failure classification, and hardware acceptance gates. Platform-specific
setup, pins, and runbooks live with the relevant product adapter.
