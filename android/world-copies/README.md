# Overte Hub serverless comparison copies

These JSON files are a reproducible, local serverless snapshot exported from the
Pico 4 during the loading investigation. They are intentionally kept separate
from the production Hub content.

- `overte-hub-original.json` is the unmodified export captured after the Hub
  scene was received by the headset (136 entities, 18 entity scripts).
- `overte-hub-pico4-optimized.json` keeps the same entity data but removes the
  measured startup-cost `sitClient.js` scripts (14 instances) and any matching
  server-side script fields. The remaining four scripts are not changed.
- `overte-hub-original-spawn.json` and `overte-hub-pico4-optimized-spawn.json`
  are test variants translated by the captured Hub center. They place the same
  scene around the packaged serverless spawn so culling/late-resource tests can
  observe the exported entities without a physics-dependent teleport.

The optimized copy is a conservative A/B fixture: geometry, transforms,
materials, and entity IDs remain unchanged. It does not pretend to be a full
authoritative replacement for the live Hub; the export API only includes the
scene entities present in the selected capture volume. The capture command used
global positions around the Hub spawn with a 2000 m radius.

For a device test, copy the desired JSON into the app cache as
`hub.json` and navigate to:

```text
file:///data/user/0/org.overte.pico/cache/hub.json
```

The Pico test runner records the same loading, resource, script, entity, and
post-screen settling metrics for both fixtures.
