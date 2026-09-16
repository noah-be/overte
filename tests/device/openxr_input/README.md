# OpenXR E2E input contract and device-free prototype

This directory defines a target-neutral command contract for the E2E operations
`input.look`, `input.move`, `tablet.open`, and `tablet.close`. Its Pico-specific
controller compiler also binds the shared `input.jump` and `input.fly`
operations without defining their platform-neutral catalog/module contract.
It also contains a pure-Python compiler and consumer state machine. The
prototype is device-free: it does **not** install an API layer, open ADB,
control a headset, or advertise an adapter capability.

The recommended runtime implementation is an **explicit, app-packaged OpenXR
API layer in an E2E-only debug APK**. OpenXR API layers are the standardized
mechanism for intercepting API calls; they avoid vendor-specific controller
drivers and informal process hooks. Khronos' Android loader can discover layer
manifests packaged below `openxr/1/api_layers/explicit.d` in APK assets. The app
must still name the explicit layer when it creates its OpenXR instance.

`XR_APILAYER_OVERTE_e2e_input` is a prototype identifier only. Khronos requires
the vendor segment of an API-layer name to be registered, and `OVERTE` is not in
the OpenXR registry at the time of this design. Before a native layer is merged,
the project must register an author tag or replace the prototype identifier with
a legitimately registered Overte tag. It must not borrow another project's tag.

## Why this boundary

The common E2E runner should say what a user does, not which Pico controller
path supplies it. A target binding profile performs the last translation:

`input.look` is not a controller path on a headset: it is an HMD/head-pose
offset. Movement and tablet operations below are controller action-state paths.
They share activation, sequencing, and watchdog transport only.

| Common operation | OpenXR test-layer state | Effect verified by the existing probe |
| --- | --- | --- |
| `input.look` | additive VIEW-reference-space orientation offset | `view.orientation` changes |
| `input.move` | bounded `XrActionStateVector2f` overlay | `avatar.position` changes |
| `input.jump` | bounded right-secondary boolean pulse | avatar rises and returns to the floor |
| `input.fly` | atomic right-secondary takeoff pulse plus bounded second hold | avatar enters flight and gains altitude |
| `tablet.open` / `tablet.close` | bounded boolean action pulse after a probe precondition | `tablet.open` reaches the requested state |

Overte's Pico OpenXR plugin already creates actions named `left_thumbstick` and
`menu_click`. It maps the thumbstick through `OpenXR.LY` to avatar locomotion,
and maps `menu_click` through `Standard.Start` to `Actions.ContextMenu`. The
tablet script also maps the off-hand secondary face button as a fallback. These
are Overte implementation details and therefore live in
[`profiles/pico4-overte.json`](profiles/pico4-overte.json), not in the common
command envelope.

The Pico profile requires right-hand dominance and advanced movement with
strafing. The debug-only Pico runtime override supplies those deterministic
preconditions without changing the user's stored movement preferences, so all
four common movement directions use the left OpenXR thumbstick.

## Contracts

- [`command-envelope.schema.json`](schemas/command-envelope.schema.json) is the
  semantic, target-neutral command envelope. The implementation additionally
  rejects a zero-distance look, duplicate IDs, booleans masquerading as JSON
  numbers, and non-finite values.
- [`binding-profile.schema.json`](schemas/binding-profile.schema.json) describes
  target-specific OpenXR action names, coordinate signs, supported directions,
  and application preconditions.
- [`session-grant.schema.json`](schemas/session-grant.schema.json) is a
  short-lived, single-sequence activation grant.
- [`protocol.py`](protocol.py) validates all three inputs and compiles a
  deterministic transition stream with observation windows and a terminal
  neutral state.
- `PrototypeConsumer` models the rule that action state changes only on
  `xrSyncActions`, delegates unknown actions, rejects replay/cross-session
  streams, and neutralizes on a watchdog or non-monotonic clock.

The semantic arguments match the shared adapter operations:

```json
{
  "schemaVersion": 1,
  "sessionNonce": "<32-to-128-lowercase-hex-characters>",
  "sequence": 1,
  "issuedEpochMs": 2000000000000,
  "commands": [
    {
      "id": "look-right",
      "operation": "input.look",
      "arguments": { "horizontal": 0.24, "vertical": 0.0 }
    },
    {
      "id": "walk-forward",
      "operation": "input.move",
      "arguments": { "direction": "forward", "durationSeconds": 0.4 }
    }
  ]
}
```

`horizontal` and `vertical` are normalized gesture fractions in the same
bounded `-0.45..0.45` range used by other target adapters. A binding profile
converts them to a bounded pose offset. Movement strength is `0.2..1.0`, and
duration is bounded. There is no generic command, script, path, shell, or raw
OpenXR function operation.

## Fail-closed activation design

The native consumer and host adapter satisfy these fail-closed activation
boundaries; a lab must still pass the physical-device gates before enabling the
adapter opt-in:

1. The layer library and its explicit manifest exist only in an E2E debug
   variant. Production/release variants do not package either file.
2. The app explicitly opts in at startup and carries the exact compile-time
   marker `OVERTE_E2E_OPENXR_INPUT_V1`.
3. An authorized local lab process writes commands by `adb shell run-as` to an
   app-private file, using a temporary file plus atomic rename. Shared external
   storage is not an input channel.
4. The consumer requires a matching nonce, exact next sequence, unexpired
   maximum-five-minute grant, exact API-layer name, and SHA-256 of the complete
   binding profile. It records the accepted sequence for the OpenXR session so
   a grant cannot be replayed.
5. Unknown fields, unknown operations/actions, invalid underlying OpenXR state,
   lost sessions, bad clocks, or parse failures produce neutral input and
   disable the consumer. They never fall back to a less constrained command.
6. Every command has a bounded observation window. Axis/button/pose overlays
   return to neutral at the end, and an independent watchdog neutralizes all
   channels if the driver disappears.
7. Cleanup deletes the app-private grant and command files and confirms a
   neutral synchronization before stopping the app.

The nonce is a stale/cross-session safety token, not authentication. The
security boundary is Android app-private storage plus an already-authorized ADB
host. A host with authorized debugging access can replace the debug APK and is
already trusted by this lab model.

## Required native API-layer behavior

The compiled stream names the minimum intercept set:

- `xrCreateAction` records handles for the exact bound Overte action names;
- `xrCreateReferenceSpace` records VIEW and stage/local handles;
- `xrSyncActions` advances one immutable test snapshot;
- `xrGetActionStateVector2f` overlays only the known locomotion action;
- `xrGetActionStateBoolean` overlays only the known tablet-toggle and vertical
  locomotion actions and maintains `changedSinceLastSync` correctly;
- `xrLocateSpace` and `xrLocateViews` compose the same additive HMD/head
  orientation offset, so Overtes head pose and rendered views agree. No
  controller action state is changed for `input.look`.

The layer must first call the next layer/runtime. It may compose test state only
when the underlying result and required position/orientation validity flags are
valid. Unknown handles and all non-test calls pass through unchanged. OpenXR
requires action query results to remain stable between `xrSyncActions` calls;
the prototype test explicitly enforces that boundary.

An explicit layer is preferred over an implicit global layer. It is scoped to
the test APK, cannot unexpectedly affect other XR applications, and can be
omitted mechanically from production packaging. Khronos' open-source SDK layer
samples should be used as the native scaffold instead of creating a loader
negotiation implementation from scratch.

## Running the prototype

Run its self-tests without a headset:

```bash
python3 -m unittest tests.device.self_tests.test_openxr_input_protocol -v
```

Inspect the binding fingerprint:

```bash
python3 tests/device/openxr_input/prototype.py fingerprint \
  --profile tests/device/openxr_input/profiles/pico4-overte.json
```

Compilation requires an explicit `--allow-prototype` flag plus valid private
grant and command JSON files. It only prints a JSON transition model; it has no
device side effects.

## Capability gate and remaining hardware work

The Android Pico adapter omits `input.look`, `input.move`, `input.jump`,
`input.fly`, `tablet.open`, and `tablet.close` by default. It advertises them
only when a qualified lab sets the explicit Debug-E2E OpenXR opt-in and supplies
a non-default, Pico-only ADB server plus a private host-state directory. That
opt-in must be enabled only after all of the following are true for the
connected test build:

- the app reports the expected build marker, consumer name, binding hash, and a
  fresh accepted session nonce;
- the API layer's package-exclusion test proves it is absent from a release APK;
- a real Pico confirms pose composition, thumbstick sign/dominant-hand state,
  reserved Menu behavior, button edge timing, neutral cleanup, and watchdog
  recovery;
- each operation's effect is independently observed through the in-client
  probe, not inferred from an API-layer acknowledgement.

Until those hardware gates pass, the current common E2E suite truthfully skips
Pico input operations instead of turning a successful protocol compile into a
false capability.

## Sources and licensing

Primary sources used for the decision:

- [OpenXR 1.1 specification](https://registry.khronos.org/OpenXR/specs/1.1-khr/html/xrspec.html),
  especially API layers, action synchronization/query behavior, reference
  spaces, view location, and the ByteDance PICO controller profiles.
- [Khronos OpenXR loader API-layer design](https://github.com/KhronosGroup/OpenXR-SDK-Source/blob/main/specification/loader/api_layer.adoc),
  including Android APK discovery paths and explicit-layer manifests.
- [Khronos OpenXR SDK Source](https://github.com/KhronosGroup/OpenXR-SDK-Source/tree/main/src/api_layers),
  the official native API-layer samples.
- [OpenXR API registry](https://github.com/KhronosGroup/OpenXR-Docs/blob/main/specification/registry/xr.xml),
  the authoritative registered author/layer tags (and the reason the current
  `OVERTE` layer name remains prototype-only).
- Overtes Pico implementation in
  `android/vr/pico/apps/picoInterface/openxr/src/OpenXrInputPlugin.cpp`,
  `interface/resources/controllers/openxr.json`,
  `interface/resources/controllers/standard.json`, and
  `scripts/system/tablet-ui/tabletUI.js`.

The prototype adds no third-party runtime dependency and uses only Python's
open-source standard library. Khronos' SDK/loader samples are open source under
Apache-2.0 and/or MIT terms; any later native layer should preserve their
license notices. No proprietary Pico SDK API is required by this design, though
the real headset still supplies its vendor OpenXR runtime.
