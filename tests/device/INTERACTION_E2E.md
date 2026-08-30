# Controlled world interaction E2E

`interaction-smoke` proves a user-facing primary action rather than merely
proving that an automation command returned success. The local fixture places
the collisionless `OVERTE_E2E_INTERACTABLE` box in front of the spawn. The
Interface probe listens to
[`Entities.mousePressOnEntity`](https://apidocs.overte.org/Entities.html#mousePressOnEntity),
which covers a mouse press and a fully pressed controller trigger on an entity.

The shared operation is deliberately semantic and small:

```text
input.primary {}
  -> {"performed": true}
```

The operation must deliver one native press/release sequence aimed at the
controlled target. The shared module records the probe count before the input
and accepts only one fresh event for the exact target. Missing and duplicate
events fail. Process restart, loss of foreground state, a missing target, or a
malformed probe is also rejected.

Product adapters implement only the physical route:

- Android and iOS Appium adapters tap the target's visible viewport point in
  the already running session. They must not call an in-client entity API.
- Linux, Windows, and macOS desktop adapters focus the verified Interface
  window and issue one native primary pointer click at the target point.
- Pico/OpenXR adapters establish a valid controller pose whose ray intersects
  the target, then issue one trigger press/release through the existing test
  API layer.

An adapter advertises `input.primary` only after a physical run archives the
before/after probe snapshots and demonstrates failure when the target is
deliberately missed. Coordinate or pose calibration is target-owned and must
not enter the shared module.
