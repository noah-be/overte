# Extended portable E2E gates

These suites extend the cross-platform baseline without importing Appium,
ADB, OpenXR, or desktop automation into shared test logic. Product adapters
translate operations; modules and assertions stay identical on every target.

## `text-input-smoke`

The adapter exposes one repository-owned, non-production text field through
`text.focus`, `text.type`, `text.snapshot`, and `text.dismiss`. The common
module enters the fixed string `Overte E2E äöüX`, removes the final character,
submits once, dismisses focus and any visible platform keyboard, and verifies
that the avatar did not move. The adapter must use the target's real input path
(desktop keyboard events, Appium/system keyboard input, or VR keyboard input).
Directly assigning the field value is not conforming.

`text.snapshot` schema version 1 contains only `value`, `focused`,
`keyboardVisible`, and `submittedCount`. `keyboardVisible` may be `null` only
where the OS has no queryable visibility API. Only fixed repository text is
collected and archived. Its machine-readable form is
`schemas/text-input-snapshot.schema.json`.

## `scripted-entity-smoke`

The serverless fixture's interaction target references
`scripted_interactable.js`. Its client entity script publishes loaded state
from `preload` and changes its own color, state, and exact activation counter
from `clickDownOnEntity`. The probe only observes these properties. One
`input.primary` must produce both one normal entity press and one fresh
script-owned mutation. This proves script resolution, download, execution,
event dispatch, and `Entities.editEntity` without an external CDN.

## `multi-user-smoke`

The ephemeral domain fixture runs a second assignment script whose only avatar
is named `OVERTE_E2E_PEER` and follows a deterministic bounded path. The probe
requires exactly one such peer and records its ephemeral session UUID,
position, observation count, and cumulative replicated movement. The module
requires movement, leaves for the controlled serverless scene, observes peer
removal, reconnects, and requires the same peer session plus fresh movement.
No account identity or production avatar data is used.

## `network-fault-recovery`

`domain.py` publishes an authenticated loopback-only control endpoint in its
private ready file. The module requests `offline`, observes disconnection while
Interface and its process remain alive, requests `online`, and requires three
fresh samples for automatic reconnection to the same domain UUID, host, and
marker set. A `finally` recovery request restores the fixture after an abort.

The endpoint controls only child process groups owned by that fixture. Its
random token is written with mode `0600`, omitted from console output, passed
through `OVERTE_E2E_DOMAIN_CONTROL_TOKEN`, and never stored in test artifacts.

## `audio-controls`

The adapter performs `audio.mute` through the product's native mute control;
the probe independently observes `Audio.muted`. The module toggles away from
the current state and always restores it in `finally`. Microphone permission
dialogs and physical acoustic capture remain optional target extensions, so
the shared suite never records audio.

## `settings-persistence`

The allowlist contains exactly the safe `audio.warn-when-muted` boolean. The
adapter changes it through a semantic product control and the probe observes
`Audio.warnWhenMuted`. The module changes the value, restarts Interface,
requires persistence, restores the original value, restarts again, and proves
that restoration also persisted. An isolated test profile is mandatory on
physical targets.

## `lifecycle-under-load`

With the controlled scene ready and tablet open, the adapter backgrounds and
reactivates the existing process. The module requires unchanged process
identity, scene readiness, tablet state, foreground state, and fresh renderer
frames, then closes the tablet. This deterministic gate precedes longer soaks.

## `render-health`

`render.snapshot` combines native presentation evidence (`backend`,
`hardwareAccelerated`, `surfaceVisible`, `blackFrame`, and monotonic
`frameSequence`) with independent `Render.getConfig("Stats").newStats` frame
progress from the probe. It rejects software rendering, hidden or black
surfaces, and either stalled evidence stream. It avoids brittle reference-pixel
comparisons. See `schemas/render-snapshot.schema.json`.

## Product-adapter promotion

All extended suites remain optional until a target branch implements and
physically accepts every advertised capability. Promotion requires a complete
physical run, stable process evidence, selector-safe diagnostics, and a verified
negative case. The domain fixture is shared; target adapters do not implement
network interruption.
