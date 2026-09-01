# Controlled world interaction E2E

`interaction-smoke` proves a user-facing primary action rather than merely
checking that an automation command returned success. The local fixture places
the collisionless `OVERTE_E2E_INTERACTABLE` box in front of the spawn. The
Interface probe observes the corresponding entity press event.

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

The deterministic mock adapter implements the complete positive and negative
contract without hardware. The integrated desktop and shared Appium adapters
do not currently advertise `input.primary`; their existing launch, session,
input, and cleanup transports are not evidence that this suite works on a real
target. A concrete target may advertise the operation only after its native
click or tap route is implemented and a physical run proves the before/after
probe transition and deliberate-miss failure.

Coordinate calibration is private target configuration. It must not enter the
shared module, committed examples, or published diagnostics.
