# Overte physical-device E2E harness

This directory is the platform-neutral orchestration layer for unattended E2E
tests on real devices. Scenarios contain no ADB, Appium, Xcode, or
operating-system branches. Target adapters translate a versioned capability
contract into those tools.

## Architecture

```text
catalog module -> OverteSession -> adapter operation -> target automation
                                      |
                                      +-> in-client Overte probe

fixture server -> controlled serverless scene
domain fixture -> ephemeral domain + assignment-owned marker scene
runner         -> lock, timeout, cleanup, JSON, JUnit, private artifacts
Jenkins        -> schedule, device reservation, history, artifact retention
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
- `domain-smoke`: launch, enter an ephemeral controlled domain, and verify its
  exact identity and assignment-owned content without restarting Interface.
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

All behavioral modules use `OverteSession` and verify effects through fresh
schema-v2 `probe.snapshot` samples. A successful input command alone is never
enough to pass a behavior.

`domain-smoke` is fully specified and hardware-free tested, but intentionally
not advertised by a real adapter yet. Adapter enablement remains a separate
per-platform acceptance step.

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
- `probe.snapshot` accepts an optional positive `afterSampleSequence` cursor;
  the returned v2 sample must advance beyond it.
- `app.stop` accepts `{}` and confirms `{"stopped": true}`.

No shared module knows controller buttons, native events, or input routes.

Concrete adapters:

- [`adapters/android/`](adapters/android/): Phone and Pico ADB lifecycle,
  installation, telemetry, and scene delivery;
- [`adapters/appium/`](adapters/appium/): shared Android/iOS W3C sessions,
  touch gestures, Accessibility, probe pull, and screenshots;
- [`adapters/mock/`](adapters/mock/): deterministic virtual state machine used
  only to prove every common scenario without hardware.

[`openxr_input/`](openxr_input/) contains the fail-closed, device-free semantic
input prototype for future Pico/OpenXR look, movement, and tablet automation.
It remains intentionally disconnected from Pico capabilities until a test-only
API layer is packaged in the debug APK and accepted on physical hardware.

Every real adapter needs a private, untracked target configuration. Copy the
relevant `targets.example.json` outside the checkout; never commit UDIDs,
device serials, local account paths, signing data, or Jenkins credentials.

## Controlled fixture and probe

[`fixture/scene.json`](fixture/scene.json) contains five local primitive
entities, including a deterministic collision wall, and no external assets.
Start an ephemeral localhost server with:

```bash
python3 tests/device/fixture/serve.py --ready-file /tmp/overte-fixture.json
```

For a phone/headset on the LAN, bind all interfaces and provide the exact
device-reachable host address:

```bash
python3 tests/device/fixture/serve.py \
  --bind 0.0.0.0 --public-host 192.0.2.10 --port 18080 \
  --ready-file /tmp/overte-fixture.json
```

The Android debug E2E APK embeds the same scene and probe and can use
`OVERTE_E2E_SCENE_URL=overte-e2e://fixture/scene`; its shell-protected launcher
maps that logical request to the fixed local asset. Release APKs contain neither
the launcher nor the two E2E assets. Signed iOS E2E builds use the HTTP fixture.
The server exposes the repository-owned probe at `/overte_e2e_probe.js`, the
pinned texture plus per-request telemetry used by `asset-smoke`, and the
deterministic sound described in [`SOUND_E2E.md`](SOUND_E2E.md). The iOS adapter
uses the probe resource only for a dedicated, runtime-attested test build; see
[`ios/`](ios/). The application target and protected signed-artifact producer
live on `apple-ios`. Fedora verifies the signed Overte/WDA handoff, installs both
IPAs, and controls physical iOS 18+ devices through the pinned RemoteXPC tunnel.
Jenkins can dispatch the producer itself, binds the exact returned workflow run
and attempt, and keeps signed bytes and populated target configuration outside
the checkout and archives.

The in-client [`probe/overte_e2e_probe.js`](probe/overte_e2e_probe.js) runs only
via Interface's existing `--testScript` mode. It records
application focus, scene readiness and markers, collision geometry, avatar
position, velocity and body yaw, `inAir`, `flying`, `flyingEnabled`, camera
orientation, tablet and optional controller state, controlled asset
resource/entity evidence, sound resource and injector state, monotonic sample
sequence, and build identity through the existing `Test.saveObject` API. It
records no audio
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

List a suite without contacting a target:

```bash
python3 tests/device/run.py \
  --adapter-manifest tests/device/adapters/android/phone.json \
  --catalog tests/device/catalog.json --suite e2e-core --list
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

Verify the device-free implementation:

```bash
python3 -m unittest discover -s tests/device/self_tests -v
python3 tests/device/fixture/serve.py --check
python3 tests/device/fixture/domain.py --check
```

Verify a configured adapter, optionally including cleanup idempotency:

```bash
python3 tests/device/verify_adapter.py \
  --adapter-manifest path/to/adapter.json --require-target --check-cleanup
```

See [`E2E_STRATEGY.md`](E2E_STRATEGY.md) for rollout, target ownership, Jenkins,
tooling decisions, and the hardware acceptance matrix.
Exact open-source tool versions, artifact checksums, and the offline validation
workflow are in [`TOOLCHAIN.md`](TOOLCHAIN.md) and
[`toolchain.lock.json`](toolchain.lock.json).
