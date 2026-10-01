# Genuine native Tablet Create acceptance

Actual stock Chromium now proves genuine native Name, Green/Blue and
Dimensions edits through independent domain observation. Subsequent ordinary Chromium and Firefox runs show intermittent lost Blue
and numeric input without a reported refusal; full edit/List-delete acceptance
remains open. All seven original entities survive exact cleanup.
[Retained source-coherent result](evidence/tablet-create-ordered-text-red-failure-20261001.json).
The first Firefox attempt failed during exact window sizing before any Tablet
UI. Its corrected exact native-density helper now reaches genuine Create UI;
the final native property gate still fails. The private atomic focus diagnostic
commits all intended properties, but its extra reads can change event timing
and are not evidence of a shipping correction. CPU contracts and menu screenshots remain separate from acceptance.

The native source routes the Shape card (`EditTabView.qml`) to
`newEntityButtonClicked/newShapeButton`. `create/edit.js` creates one domain
Shape/Cube, selects that actual entity, and switches to Properties. The native
Properties WebEngine page exposes Name, Shape/Color, and Transform/Dimensions.
The List WebEngine app sends its genuine selection/deletion event to the
unchanged native Create selection manager.

The runner admits only `overte://127.0.0.2:45102` behind an owned loopback gateway.
It first starts a fresh, permanently muted native observer without default scene
provisioning and requires exactly the seven existing `Browser Lab ` entities.
The UUID/name/type baseline stays in private evidence; portable evidence contains
only its hash. Only a single unlocked newly added domain Cube with no children
can be latched after the GUI Shape click. Ambiguous additions abort the probe.

First run discovery, from `browser-client`, with the existing managed services
running, no other gateway join in progress, and the stock browser variables:

```sh
OVERTE_CREATE_DISCOVERY=1 OVERTE_LAB_URL=http://127.0.0.1:8090 \
  node tests/integration/tablet-create.mjs
```

Discovery captures the **actual** native Properties and List PNGs and then
removes only its native-latched fixture in `finally`. It explicitly reports
`functionalAcceptance: false`. Inspect those captured pages to produce the
version-1 coordinate map. Do not guess field positions or reuse People controls.
The map includes `propertiesPNG_SHA256`, `listPNG_SHA256` and native 480×706
coordinate pairs for `name`, `shapeTab`, `colorRed`, `colorGreen`, `colorBlue`,
`transformTab`, `dimensionX`, `dimensionY`, `dimensionZ`, `listSearch`, `listRow`,
`listDelete`. Every field coordinate must be below the 40-pixel Create tab bar.

```sh
OVERTE_CREATE_COORDINATES=/absolute/private/calibrated-map.json \
  OVERTE_LAB_URL=http://127.0.0.1:8090 node tests/integration/tablet-create.mjs
```

Full mode uses real pointer/keyboard/composition input through the browser Tablet
canvas. It asserts independent native and received browser properties for the
unique UUID name, RGB `(30,170,220)`, and dimensions `(0.7,0.9,1.1)` meters. Before
List deletion it requires a **new actual native `setSelections` log event**
containing exactly its own UUID. The log is read only from the single fresh
worker profile created by this join. A missing/ambiguous profile, missing native
selection record, foreign or multi-selection refuses deletion. A refreshed
exact baseline must be present afterward in native and browser observations.

Native cleanup never edits properties and never deletes a baseline entity or
children. A failed UI flow permits only finally deletion of the exact native
ownership latch. Failed and discovery runs retain PNGs/private logs and their
failure report. Each source hash must match at start/end. The known audited
2026.04.1 native executable hash and actual packaged Create scripts are recorded.
Geometry counts are diagnostic only because asynchronous avatars and native UI
helpers can allocate other geometries; no numeric counter is claimed to prove
visual Shape pixels. A true pixel/visual assertion remains separate from the
native/browser property-delivery proof.

CPU validation:

```sh
node --test --test-isolation=none --test-reporter=spec \
  tests/integration/tablet-create-contract.test.mjs
```

Eight contracts cover private/local admission, exact baseline/single ownership,
ambiguous/child-owning refusal, property correspondence, calibration bounds,
actual production observer factory cleanup, real native selection log ownership,
and cleanup when an initial native frame timeout occurs before the observer tick.
