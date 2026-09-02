# Extended portable E2E gates

These suites extend the target-neutral control plane. Their common modules,
schemas, fixtures, execution recipes, and deterministic mock coverage are
integrated. Production-target support remains `implemented`, not physically
accepted, until a concrete adapter advertises the required capabilities and
supplies governed evidence.

## `text-input-smoke`

The adapter exposes one repository-owned, non-production text field through
`text.focus`, `text.type`, `text.snapshot`, and `text.dismiss`. The common
module enters fixed Unicode text, removes the final character, submits once,
dismisses focus and any observable platform keyboard, and verifies that the
avatar did not move. Directly assigning the field value is not conforming.

`text.snapshot` schema version 1 contains only `value`, `focused`,
`keyboardVisible`, and `submittedCount`. `keyboardVisible` may be `null` only
where the target has no queryable visibility API. Only fixed repository text
is collected and archived. Its machine-readable form is
[`schemas/text-input-snapshot.schema.json`](schemas/text-input-snapshot.schema.json).

## `scripted-entity-smoke`

The serverless fixture's interaction target references
`fixture/scripted_interactable.js`. Its client entity script publishes loaded
state from `preload` and changes its own color, state, and exact activation
counter from the entity press event. The probe only observes these properties.
One `input.primary` must produce both a normal entity press and one fresh
script-owned mutation.

## `multi-user-smoke`

The ephemeral domain fixture runs a second assignment script whose only avatar
is named `OVERTE_E2E_PEER` and follows a deterministic bounded path. The probe
requires exactly one such peer and records its ephemeral session UUID,
position, observation count, and cumulative replicated movement. The module
requires movement, observes departure, reconnects, and requires the same peer
session plus fresh movement. No account identity or production avatar data is
used.

## `network-fault-recovery`

`fixture/domain.py` publishes an authenticated loopback-only control endpoint
in its private ready file. The module requests `offline`, observes
disconnection while Interface and its process remain alive, requests `online`,
and requires fresh samples for automatic reconnection to the same domain UUID,
host, and marker set. A `finally` recovery request restores the owned fixture.
The random token is omitted from console output and artifacts.

## `audio-controls` and `settings-persistence`

`audio-controls` asks the adapter to toggle the product's native mute control;
the probe independently observes `Audio.muted`, and the module restores the
baseline in `finally`. `settings-persistence` changes only the allowlisted
`audio.warn-when-muted` boolean, proves it across a restart, restores it, and
proves the restoration across another restart. Physical acoustic capture and
production profile data are outside these shared contracts.

## `lifecycle-under-load` and `render-health`

With the controlled scene ready and tablet open, `lifecycle-under-load`
backgrounds and reactivates the existing process. It requires unchanged
process identity, content, tablet state, foreground state, and fresh frames.
`render-health` combines native presentation evidence with independent probe
frame progress. It rejects software rendering, a hidden or black surface, and
either stalled evidence stream. See
[`schemas/render-snapshot.schema.json`](schemas/render-snapshot.schema.json).

## Promotion boundary

The integrated real-target adapters advertise only operations they implement.
None of the shared mock results in this document is hardware acceptance.
Promotion requires a complete physical run, stable process evidence,
selector-safe diagnostics, and a verified negative case for every newly
advertised capability. Android-, iOS-, Pico-, or other platform work not yet
integrated into `main` is not implied by these contracts.
