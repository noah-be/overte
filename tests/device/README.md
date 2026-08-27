# Overte physical-device E2E harness

This directory is the platform-neutral orchestration layer for unattended E2E
tests on real devices. Scenarios contain no ADB, Appium, Xcode, OculiX, or
operating-system branches. Target adapters translate a versioned capability
contract into those tools.

## Architecture

```text
catalog module -> OverteSession -> adapter operation -> target automation
                                      |
                                      +-> in-client Overte probe

fixture server -> controlled serverless scene
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
- `asset-smoke`: controlled local texture delivery, ready resource state,
  uniquely tagged Image-entity use, and stable process/foreground evidence.
  Test logic is implemented; all real-adapter activation remains pending. See
  [`ASSET_LOAD_E2E.md`](ASSET_LOAD_E2E.md).
- `e2e-core`: launch, controlled scene load, look, movement, and tablet
  open/close behavior.
- `accessibility`: Appium native-tree audit against explicitly configured
  stable QML accessibility labels.
- `stability`: idle process/foreground health on every target, with strict
  battery, memory, and thermal samples when the adapter advertises telemetry.
- `lifecycle-stability`: repeated background/activation cycles with a stable
  process identity on Android and iOS. Desktop profiles do not select it.

Enable long suites only after the short suites are reliable on the target.

The `scene`, `look`, `move`, and `tablet` modules use `OverteSession` and verify
effects through `probe.snapshot`. An input command succeeding is never enough
to pass a behavior.

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

Concrete adapters:

- [`adapters/android/`](adapters/android/): Phone and Pico ADB lifecycle,
  installation, telemetry, and scene delivery;
- [`adapters/appium/`](adapters/appium/): shared Android/iOS W3C sessions,
  touch gestures, Accessibility, probe pull, and screenshots;
- [`adapters/desktop_oculix/`](adapters/desktop_oculix/): one visual-input
  implementation for Linux, Windows, and macOS;
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

[`fixture/scene.json`](fixture/scene.json) contains four local primitive
entities and no external assets. Start an ephemeral localhost server with:

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
the launcher nor the two E2E assets. Desktop targets use the HTTP fixture. The
fixture server also exposes the repository-owned probe at
`/overte_e2e_probe.js` and the pinned texture plus request telemetry used by
`asset-smoke`. The iOS adapter uses that probe resource only for a dedicated,
runtime-attested test build; see [`ios/`](ios/). The application target and
protected signed-artifact producer live on `apple-ios`. Fedora verifies the
signed Overte/WDA handoff, installs both IPAs, and controls physical iOS 18+
devices through the pinned RemoteXPC tunnel. Jenkins can dispatch the producer
itself, binds the exact returned workflow run and attempt, and keeps signed
bytes and populated target configuration outside the checkout and archives.

The in-client [`probe/overte_e2e_probe.js`](probe/overte_e2e_probe.js) runs
only via Interface's existing `--testScript` mode. It records application
focus, scene URL/readiness/entity markers, avatar position, camera orientation,
tablet state, and Overte build identity through the existing `Test.saveObject`
API.

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
