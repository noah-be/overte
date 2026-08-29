# Semantic tablet E2E contract

The `tablet-e2e` suite is the platform-neutral behavioral baseline for the
system tablet. It is separate from `e2e-core`: the existing core suite keeps
its small, widely implemented open/close check, while this suite requires a
complete semantic UI adapter and an external product policy.

## Version 1 operations

The capability registry defines two semantic operations in addition to the
existing `tablet.open` and `tablet.close` operations:

- `tablet.snapshot` accepts `{}` and returns a tablet UI contract version 1,
  snapshot schema version 1 object:

  ```json
  {
    "contractVersion": 1,
    "schemaVersion": 1,
    "screenId": "settings.home",
    "ready": true,
    "visibleControlIds": ["nav.home", "settings.general"],
    "selectedControlIds": []
  }
  ```

- `tablet.activate` accepts
  `{"contractVersion": 1, "controlId": "app.settings"}` and returns
  `{"performed": true}`. The result confirms that automation was performed;
  the following stable snapshot is the behavioral proof.

`selectedControlIds` is optional. When present it is sorted, unique and a
subset of `visibleControlIds`. Every field is closed: unknown versions,
screens, controls or fields, malformed values, duplicates and unsorted ID
lists are infrastructure errors. The complete vocabulary is
[`tablet-ui-contract.json`](tablet-ui-contract.json), and the wire shape is
[`schemas/tablet-ui-snapshot.schema.json`](schemas/tablet-ui-snapshot.schema.json).

An adapter reports what the application exposes. It does not receive the
selected product-policy path. Shared orchestration polls until it receives at
least two identical snapshots with the expected `screenId` and `ready: true`.
Only then may it assert that a forbidden control is absent.

## Semantic IDs

Screen IDs in v1 are:

- `tablet.home`
- `settings.home`
- `settings.general`
- `settings.graphics`
- `settings.audio`
- `settings.security`
- `settings.controllers`

Control and feature IDs in v1 are:

- `app.settings`
- `settings.general`
- `settings.graphics`
- `settings.audio`
- `settings.security`
- `settings.controllers`
- `settings.hmd-preferences`
- `settings.vr-render-resolution`
- `nav.back`
- `nav.home`
- `nav.close`

IDs are non-localized behavior names. Visible captions, translated
accessibility descriptions, operating systems, product names, coordinates,
screenshots and native selector syntax are not part of this contract. The
existing QML implementation flag `picoResolutionSettingsAvailable` is mapped
to the shared `vrRenderResolutionAvailable` presentation capability; it is not
an E2E capability or semantic ID.

## Product policy version 1

A policy has a public, non-secret `profileId` and sorted expectations keyed by
screen. Every expected nested screen declares the semantic control used to
enter it from `settings.home`:

```json
{
  "contractVersion": 1,
  "schemaVersion": 1,
  "profileId": "example.touch-profile",
  "expectations": {
    "settings.home": {
      "entryControlId": "app.settings",
      "requiredControlIds": ["nav.home", "settings.general"],
      "forbiddenControlIds": ["settings.controllers"]
    },
    "tablet.home": {
      "requiredControlIds": ["app.settings", "nav.close"],
      "forbiddenControlIds": []
    }
  }
}
```

The validator requires `tablet.home` and `settings.home`, rejects conflicting
expectations, and requires each nested entry control on `settings.home`.
[`schemas/tablet-product-policy.schema.json`](schemas/tablet-product-policy.schema.json)
documents the wire format. The checked-in `mock-flat-touch.json` and
`mock-vr-render-resolution.json` policies are deterministic contract proofs,
not shipping product claims.

## Baseline sequence

One controlled application process is reused. The module establishes a closed
state, opens through `tablet.open`, confirms open through `probe.snapshot`,
stabilizes `tablet.home`, activates Settings by ID, stabilizes and evaluates
`settings.home`, visits every additional policy screen and returns with
`nav.back`, returns to Tablet Home with `nav.home`, closes through
`tablet.close`, confirms closed through the probe, and checks the original
process identity throughout.

Strict runs provide the policy explicitly:

```bash
python3 tests/device/run.py \
  --adapter-manifest tests/device/adapters/mock/adapter.json \
  --catalog tests/device/catalog.json --suite tablet-e2e \
  --tablet-policy tests/device/policies/mock-flat-touch.json \
  --allow-virtual --require-complete
```

Set `OVERTE_MOCK_TABLET_UI_PROFILE=vr` and select the VR mock policy for its
independent positive proof. JSON diagnostics contain only validated semantic
state and policy evaluation. Screenshots remain opt-in failure diagnostics and
are never truth evidence.

## Product-adapter handoff

After this shared contract is reviewed on `main`, each product branch owns its
native implementation and real policy:

- Android Phone (`android-phone`): implement semantic observation and user
  activation in its existing product adapter, and add a Flat-Touch policy.
- iOS/iPadOS (`apple-ios`): implement the same two operations using its native
  automation boundary, and add its own Flat-Touch policy.
- Pico 4 (`android-vr-pico`): implement the operations in its product adapter,
  map the existing render-scale UI to `settings.vr-render-resolution`, and add
  a policy requiring the HMD, controller and render-resolution features.

Product sessions may change their product adapter implementation, manifest,
private external target configuration, product policy and product acceptance
tests. They should not independently change `contracts.py`, `capabilities.json`,
`catalog.json`, `tablet-ui-contract.json`, the shared schemas, `run.py`,
`overte_session.py`, `modules/tablet_e2e.py`, the shared QML semantic IDs or
the mock policies. A needed shared-contract revision must return to a
`main`-derived review and increment the appropriate version.

Native transports, target selectors and device configuration stay out of the
shared module. A target advertises `tablet.snapshot` and `tablet.activate` only
when both are executable. Missing required operations are completeness errors
under `--require-complete`; a forbidden product feature is an assertion
failure, never a missing capability or skip.
