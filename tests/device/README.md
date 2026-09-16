# Overte physical-device E2E harness

The lifecycle policy, common CI flow, evidence contracts, stability campaign,
and portable suite frontier are documented in
[`CROSS_PLATFORM_OPERATIONS.md`](CROSS_PLATFORM_OPERATIONS.md).

This directory contains the platform-neutral orchestration layer for device
and desktop E2E tests. Scenarios contain no operating-system, packaging, or
transport details. The integrated desktop and shared Appium adapters translate
only their advertised versioned capabilities into transport operations.

## Architecture

```text
catalog module -> OverteSession -> adapter operation -> target automation
                                      |
                                      +-> in-client Overte probe

fixture server -> controlled serverless scene
domain fixture -> ephemeral domain + assignment-owned marker scene
runner         -> lock, timeout, cleanup, JSON, JUnit, private artifacts
matrix         -> selector-free policy evaluation
```

The runner reserves exactly one target for a complete run, applies module
timeouts to process groups, always calls idempotent cleanup, redacts private
selectors, and stores diagnostics outside the source tree. Exit code `0`
passes, `77` skips for a missing optional capability, `75` reports device-lab
infrastructure failure, and other non-zero codes report an application
assertion failure.

## Portable suites

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
- `domain-recovery`: leave the controlled domain for the local fixture and
  re-enter it with stable content and process identity.
- `interaction-smoke`: prove that one semantic primary action produces exactly
  one event on the controlled interaction target; see
  [`INTERACTION_E2E.md`](INTERACTION_E2E.md).
- `text-input-smoke`, `scripted-entity-smoke`, `multi-user-smoke`,
  `network-fault-recovery`, `audio-controls`, `settings-persistence`,
  `lifecycle-under-load`, and `render-health`: extended common contracts
  documented in [`PORTABLE_EXTENDED_E2E.md`](PORTABLE_EXTENDED_E2E.md).
- `vertical-locomotion`: one jump with observed ascent and landing, followed by
  bounded flight with observed active ascent. Adapters lacking either input
  capability skip only the corresponding module unless `--require-complete`
  is selected.
- `accessibility`: Appium native-tree audit against explicitly configured
  stable QML accessibility labels.
- `stability`: idle process/foreground health on every target, with strict
  battery, memory, and thermal samples when the adapter advertises telemetry.
- `lifecycle-stability`: repeated background/activation cycles with a stable
  process identity on Android and iOS.

Enable long suites only after the short suites are reliable on the target.

Modules that assert in-client effects use `OverteSession` and verify those
effects through fresh schema-v2 `probe.snapshot` samples. A successful input
command alone is never enough to pass a behavior.

These suites are fully specified and hardware-free tested. Advertisement by a
real adapter remains a separate capability decision, and the empty evidence
registry means no production suite is currently documented as physically
accepted.

## Adapter protocol

An adapter manifest uses schema version 1:

```json
{
  "schemaVersion": 1,
  "id": "android-phone-adb",
  "command": ["adapter.py", "--kind", "phone"]
}
```

The executable receives one command and writes exactly one JSON value:

```text
adapter discover
adapter describe --target TARGET
adapter invoke --target TARGET --operation OPERATION --arguments JSON
adapter cleanup --target TARGET
```

`discover` returns `selector`, `displayName`, `platform`, `physical`, and a
sorted `capabilities` list. Selectors are private transport identifiers and
must never appear in descriptions or persisted output. Supported names and
operation results are versioned in [`capabilities.json`](capabilities.json).
Machine-readable catalog, manifest, and probe schemas are in [`schemas/`](schemas/).

The common input and lifecycle contract is deliberately small:

- `input.jump` accepts `{}` and returns at least `{"performed": true}`.
- `input.fly` accepts only `{"durationSeconds": NUMBER}`, bounded from `0.1`
  through `10.0`, and returns at least `{"performed": true}`.
- `input.look` accepts bounded non-zero horizontal and vertical components;
  positive values mean right and up.
- `input.move` accepts one of `forward`, `backward`, `left`, or `right` and a
  duration from `0.1` through `10.0` seconds.
- `input.primary` accepts `{}` and reports a performed native action; the probe,
  not that response, proves delivery to the controlled entity.
- `text.focus`, `text.type`, `text.snapshot`, and `text.dismiss` expose only the
  repository-owned fixed-text contract.
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
every common scenario without hardware. The integrated
[`adapters/desktop_oculix/`](adapters/desktop_oculix/) and
[`adapters/appium/`](adapters/appium/) implementations advertise smaller,
truthful capability sets. The shared Appium layer contains no Android or iOS
product implementation history. Real target configuration must remain outside
the checkout; never commit device identifiers, account paths, signing data, or
CI credentials.

## Controlled fixture and probe

[`fixture/scene.json`](fixture/scene.json) contains six local primitive
entities, including a deterministic collision wall and scripted interaction
target, and no external assets. Validate the fixture without opening a
long-running listener:

```bash
python3 tests/device/fixture/serve.py --check
```

The Android debug E2E APK embeds the same scene and probe and can use
`OVERTE_E2E_SCENE_URL=overte-e2e://fixture/scene`; its shell-protected launcher
maps that logical request to the fixed local asset. Release APKs contain neither
the launcher nor the two E2E assets.

The server exposes the repository-owned probe at `/overte_e2e_probe.js` and the
pinned texture plus per-request telemetry used by `asset-smoke`, together with
the deterministic sound described in [`SOUND_E2E.md`](SOUND_E2E.md). The
in-client [`probe/overte_e2e_probe.js`](probe/overte_e2e_probe.js) records
application focus, scene readiness and markers, collision geometry, avatar
position, velocity and body yaw, `inAir`, `flying`, `flyingEnabled`, camera
orientation, tablet state, controlled asset resource/entity evidence, sound
resource and injector state, world-interaction and entity-script state,
controlled peer replication, monotonic sample sequence, and build identity
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
domain-server and assignment-client stack. The `domain-smoke` assertion waits
for the exact `/id` UUID, host, all repository-owned domain markers, stable
entity samples, foreground state, and unchanged process identity. See
[`fixture/DOMAIN.md`](fixture/DOMAIN.md) for the local run and environment
handoff.

## Running

List the common suite against the deterministic adapter:

```bash
python3 tests/device/run.py \
  --adapter-manifest tests/device/adapters/android/phone.json \
  --catalog tests/device/catalog.json --suite e2e-core --list
```

Run representative suites in one ephemeral directory:

```bash
run_root="$(mktemp -d)"
OVERTE_MOCK_E2E_STATE="$run_root/vertical-state.json" \
python3 tests/device/run.py \
  --adapter-manifest tests/device/adapters/mock/adapter.json \
  --catalog tests/device/catalog.json --suite vertical-locomotion \
  --output-dir "$run_root/vertical" --allow-virtual --require-complete

OVERTE_MOCK_E2E_STATE="$run_root/tablet-state.json" \
OVERTE_MOCK_TABLET_UI_PROFILE=flat python3 tests/device/run.py \
  --adapter-manifest tests/device/adapters/mock/adapter.json \
  --catalog tests/device/catalog.json --suite tablet-e2e \
  --tablet-policy tests/device/policies/mock-flat-touch.json \
  --output-dir "$run_root/tablet" --allow-virtual --require-complete
```

Run on one discovered physical target and keep results outside the checkout:

```bash
python3 tests/device/run.py \
  --adapter-manifest tests/device/adapters/android/phone.json \
  --catalog tests/device/catalog.json --suite smoke \
  --output-dir /tmp/overte-device-run
```

Jenkins runs suites with `--require-complete`, so a target that lacks any
capability required by the selected suite is an infrastructure error instead of
a misleading partial pass. Use that flag for manual acceptance runs as well.

Use `--target` only when discovery yields multiple targets. The value is never
persisted, but shell tracing must still be disabled around it in CI.

Verify the device-free implementation through the project entry point:

```bash
python3 tests/device/run_control_plane_tests.py --profile quick
python3 tests/run-project-tests.py --suite documentation
```

Inspect the reusable adapter verifier without selecting or contacting a target:

```bash
python3 tests/device/verify_adapter.py --help
```

See [`E2E_STRATEGY.md`](E2E_STRATEGY.md) for rollout, target ownership, Jenkins,
tooling decisions, and the hardware acceptance matrix.
Exact open-source tool versions, artifact checksums, and the offline validation
workflow are in [`TOOLCHAIN.md`](TOOLCHAIN.md) and
[`toolchain.lock.json`](toolchain.lock.json).
