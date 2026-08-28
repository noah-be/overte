# Overte device E2E harness

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
runner         -> lock, timeout, cleanup, JSON, JUnit, private artifacts
```

The runner reserves exactly one target for a complete run, applies module
timeouts to process groups, always calls idempotent cleanup, redacts private
selectors, and stores diagnostics outside the source tree. Exit code `0`
passes, `77` skips a missing optional capability, `75` reports device-lab
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
- `e2e-core`: launch, controlled scene load, look, movement, and tablet
  open/close behavior.
- `domain-smoke`: launch, enter an ephemeral controlled domain, and verify its
  exact identity and assignment-owned content without restarting Interface.
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

The `scene`, `look`, `move`, and `tablet` modules use `OverteSession` and
verify effects through `probe.snapshot`. A successful input command alone is
never enough to pass a behavior.

`domain-smoke` is fully specified and hardware-free tested, but intentionally
not advertised by a real adapter yet. Adapter enablement remains a separate
per-platform acceptance step.

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
sorted `capabilities` list. Selectors are private transport identifiers and
must never appear in descriptions or persisted output. Supported operation
names and results are versioned in [`capabilities.json`](capabilities.json).
Machine-readable catalog, manifest, and probe schemas are in
[`schemas/`](schemas/).

The vertical-locomotion adapter contract is deliberately small:

- `input.jump` accepts `{}` and returns at least `{"performed": true}`.
- `input.fly` accepts only `{"durationSeconds": NUMBER}`, bounded from `0.1`
  through `10.0`, and returns at least `{"performed": true}`.

No shared module knows controller buttons, native events, or input routes.

[`adapters/mock/`](adapters/mock/) is a deterministic state machine that proves
every common scenario without hardware. Concrete adapters, private target
configuration examples, installation logic, and platform toolchains belong to
their product branches. Real target configuration must remain outside the
checkout; never commit device identifiers, account paths, signing data, or CI
credentials.

## Controlled fixture and probe

[`fixture/scene.json`](fixture/scene.json) contains four local primitive
entities and no external assets. Start an ephemeral localhost server with:

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
application focus, scene readiness and markers, avatar position, `inAir`,
`flying`, `flyingEnabled`, camera orientation, tablet state, controlled asset
resource/entity evidence, sound resource and injector state, and build identity
through Interface's existing test-script result API. It records no audio
samples. Product adapters own the exact launch and result transport used to
load it. An adapter may place a mode-0600 `e2e-client-command.json` beside its
private probe copy. The probe accepts only strict, versioned navigation,
controlled local Image-entity, and fixture sound-channel commands; a
network-loaded probe without that file stops polling the private channel.

[`fixture/domain.py`](fixture/domain.py) owns the complementary ephemeral
domain-server and assignment-client stack. The `domain-smoke` assertion waits
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
```

Use `--target` only when discovery yields multiple targets. The value is never
persisted, but shell tracing must still be disabled around it in CI.

Verify the device-free implementation:

```bash
python3 -m unittest discover -s tests/device/self_tests -v
python3 tests/device/fixture/serve.py --check
python3 tests/device/fixture/domain.py --check
```

Every target adapter should also pass the reusable protocol verifier. The
optional cleanup check calls cleanup twice and verifies idempotency directly:

```bash
python3 tests/device/verify_adapter.py \
  --adapter-manifest path/to/adapter.json --require-target --check-cleanup
```

See [`E2E_STRATEGY.md`](E2E_STRATEGY.md) for the shared behavior contract,
failure classification, and hardware acceptance gates. Platform-specific
setup, pins, and runbooks live with the relevant product adapter.
