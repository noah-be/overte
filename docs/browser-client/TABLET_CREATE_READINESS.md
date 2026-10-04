# Native Create readiness calibration

The previous discovery result preserved all seven baseline entities and removed
its one owned Cube. It did **not** prove usable Properties or List pages. Both
captured native PNGs contained gray skeleton controls; the supposed List PNG was
still Properties. The old `darkPixels > 10000` check accepted the page background,
and the first changed capture did not establish the requested native tab route.

Packaged `edit-style.css` resolves its native font URLs to the existing release
`usr/bin/resources/fonts` directory. The worker mounts that exact release, `/usr`
and `/etc/fonts`. Missing font files have not been demonstrated. The independent
observer's log has no font failure, but it is not the worker displaying Create.
The diagnostic below observes that actual worker without modifying the app DOM.

## Separate test gateway

Run from the reviewed client directory after source freezes:

```sh
node tests/integration/prepare-tablet-create-audit.mjs "$PWD"
```

This writes a private temporary gateway copy and returns its entry path. Launch
that entry using the existing isolated managed-domain configuration, a dedicated
gateway port and matching browser Origin. Keep the ordinary gateway unchanged.
The copied helper alone gains the fixed diagnostic; there is no browser command,
JavaScript source argument or remote evaluation endpoint. The copied gateway's
`dist`, `public` and dependencies refer read-only to the reviewed build. Do not
change that build during the test.

Point `OVERTE_LAB_URL` at the test gateway and run normal discovery with the same
stock browser, private native observer and exact local-domain ownership guards:

```sh
OVERTE_CREATE_DISCOVERY=1 node tests/integration/tablet-create.mjs
```

Before the Shape click, the runner verifies that the fresh worker contains the
exact instrumented capture QML derived from the shipping helper. It records that
runtime SHA separately. A normal gateway refuses this audit rather than rezzing
an entity without readiness instrumentation.

## Fixed passive observation

For a visible WebEngine descendant whose URL is exactly the packaged Properties
or List page, each capture runs one fixed read-only query. At most four views,
4096 QML nodes and one pending callback per route are admitted. The query reports
document readiness, EventBridge availability, bounded font states and fixed
control rectangles. It does not invoke EventBridge, set a property, insert text,
read arbitrary URLs, export input contents or accept browser-provided selectors.
Only the UUID-shaped current Properties selection is retained in the private
worker log for comparison with the single own observer latch. Reports omit it.

The runner requires an exact displayed capture sequence/revision and requested
route, completed document, EventBridge, initialized controls, loaded native fonts
and a nonempty List. Properties additionally requires the single owned UUID and
an enabled Name field. Actual UUID/Search glyph pixels must be visible inside
the respective control, excluding borders and uniform gray skeleton blocks.
No Create edits use direct DOM or native entity-property writes.

If the 30-second readiness deadline fails, retain the PNG and the last bounded
route/font/control diagnostic. This distinguishes a wrong tab, delayed native
font loading, missing EventBridge/selection data and a real painting failure.
Do not classify any of these as successful calibration.

Only CPU contracts have been run for this proposal. A genuine native Qt discovery
and complete Shape/Properties/List edit-and-delete journey remain required.
