# Actual Hub passive census qualification

This followup wires the reviewed async World diagnostic into the existing actual
Hub journey. It is disabled unless `OVERTE_LAB_ASYNC_DRAW_CENSUS=1`. The diagnostic
never changes permissions, model resources, matrices, collisions, materials,
renderer settings or instance admission. The existing synchronous census option
remains separate and unchanged.

Run the existing source-attested Hub command with its existing gateway/browser
environment and add:

```sh
OVERTE_LAB_ASYNC_DRAW_CENSUS=1 OVERTE_LAB_RECONNECT=1 node tests/integration/public-hub.mjs
```

Run that command from `browser-client`. Retain the same current stock-browser
selection, actual GPU/desktop, fluidity requirements and owned-service setup used
by the existing Hub qualification. This flag does not start a service or change
any browser flags. Do not enable the separate legacy synchronous census when
comparing this diagnostic's cost.

One call follows the initial stored steady/walking/native-pose gates and world
screenshot, immediately before leaving. A second call, only if reconnect is
already requested, follows the rejoined stored steady/walking/native-pose gates
and precedes that generation's leave. Each admitted ordinal is attempted only
once, including refused attempts; there is no retry. Reconnect constructs the
usual fresh World and performance ring. The original movement, pose agreement,
load deadlines, reconnect and fluidity gates remain unchanged. Census work is
not added to their already-copied acceptance samples.

The World owns its reviewed 5-second diagnostic wall timer. The collector adds a
separate 6-second failure guard for a missing/broken settling contract; it does
not extend any existing journey deadline. Its timer is cleared on every exit,
late hook rejection is consumed, and the existing harness finally closes the
browser on failure. A missing hook, ended admission or malformed report fails
with fixed messages, never a reflected native hook exception.

The start/end source manifests now include the async World helper and this exact
serializable page collector. An opt-in run refuses a missing helper source hash
before starting the browser. Existing distribution manifests still attest the
actual JS/WASM/CSS. Save those hashes, the browser version and the paired initial
and rejoined census results with the actual journey report; an old library CPU
fixture is not a substitute for this measurement.

The collector projects only fixed scalar/count/group fields and known refusal
or hook enums. It removes arbitrary scope/unresolved strings, extra fields and
all opaque alpha-state JSON keys. Alpha states become two counts. It preserves
partial coverage, observed owner/mesh/part counts, charged geometry/metadata work,
actual task/CPU/wall timings, geometry identity versus byte-class counts,
material/Source/sampler counts, and both repeated-geometry grouping categories.
It validates the original resource ceilings and group arithmetic. A counted
terminal censorship turn can make `taskSlices=1025` only when the scan is partial
and explicitly reports `slice-count-budget` (1024 scan turns plus termination).

Interpret `partial` and `reasons` first. A censored result with zero groups says
nothing about absent repetition. A complete result can describe byte-equal
geometry with exact material identity versus audited material-value equality,
but remains passive research: shared resource leases, edit restoration,
picking/collision ownership, per-instance culling/shadows/lighting and native
rights are still required before instancing. Rejected dynamic owner counts are
per-turn observations, not an atomic frozen moving scene. Nothing in this
measurement authorizes optimization or relaxes a Firefox performance gate.

The collector itself occupies wall/CPU time after gates; overall CPU profiles,
GL totals, final live performance rings and process durations may therefore
include it. Its `startedAt`/`finishedAt` timestamps identify that interval. Use
the existing stored initial/rejoined acceptance samples when comparing fluidity,
not `finalDiagnostics.state.performance` after the census.

Eight portable Node/VM contracts pass without launching a browser, native
worker, X server, gateway or public-world connection. They test exact function
serialization, one-attempt semantics, partial results, fixed-enum projection,
malformed resource/group bounds, disconnection, real never-settling promises
with controlled deadline firing, consumed late rejection and unchanged harness
call ordering/deadlines/gates. Ordinary `tests/*.test.mjs` discovery includes them:

```sh
node --test tests/hub-async-draw-census.test.mjs
```

Two sequential actual stock cohorts now run this exact collector against the
published09c062 runtime: Chromium154 and Firefox156, with74 start/end source
pins and unchanged distribution manifests. Chromium passes all original loading,
movement/native agreement, rejoin and four fluidness gates. Firefox loads and
synchronizes/rejoins but fails all four fluidness gates. Each engine records two
partial censuses. Chromium stops on owner-revision changes; Firefox reaches the
unchanged2MiB metadata ceiling. Unsupported node refusals remain unclassified
beyond their existing enum. Full coverage, eligible instancing count, speed gain
and Firefox fluidity improvement remain unproved. See the
[source-bound actual outcome](evidence/hub-async-draw-census-stock-20261002.json).

## Captured loaded-Model subset

The separate optional `OVERTE_LAB_LOADED_MODEL_COHORT_CENSUS=1` flag invokes
`window.__overte.drawModelCohortAsync()` once after each admission's unchanged
stored movement/native/fluidness gates. Use the same command and owned gateway
environment above, substituting that flag for the whole-world flag. No hook is
called automatically. Its report selects at most64 static loaded Model owners
and always states `wholeWorldCoverage:false`; `selectionPartial` reports a larger
eligible source population. Never combine different captures into whole-world
coverage or an instancing admission claim.

The request captures selected root/status/shader revision, bounded plain native
entity semantics, signatures, dependencies and scene/local/world transforms.
Semantically equal native record clones are allowed; selected revisions/removals,
material dependencies, authority revocation and changes to the selected prefix
censor every group. Unrelated nonselected dynamic/non-Model updates remain outside
this explicit scope. The scanner still verifies watched graph/resource
descriptors, geometry bytes, materials, samplers and supported prototypes. It
captures a resource when first read, rather than atomically snapshotting all
graphs at request entry; the result remains a passive diagnostic.

Original ceilings remain1024 roots,16384 source entities/nodes,8192 parts,64MiB
geometry,2MiB aggregate metadata,2000ms active CPU and five seconds wall time.
Bounded synchronous source preparation is reported and deducted from the same
continuation CPU/wall budgets; an overrun immediately revokes scanning. The
single request slot cancels/releases its previous owner before capture. All
terminal paths release timers, listeners and source references. Fixed refusal
details distinguish native record revisions and unsupported Light/Camera/Sprite
prototypes without admitting those classes or retaining names/IDs/URLs.

The source/collector hashes are included in the existing start/end manifests.
Portable contracts cover explicit subset scope, selected revisions, unrelated
updates, resource mutations, replacement/abort cleanup, unchanged original Hub
gates and private-field projection. The new actual stock Chromium154/Firefox156
pair captures this diagnostic twice per engine with78 unchanged source pins and
unchanged distributions. Every capture selects64 of241 eligible owners and
remains partial: the recorded prefix covers one owner,27 nodes and24 draw parts
before the original wall/CPU ceilings censor continuation. All groups remain
censored; zero groups cannot establish absent repetition or a speed gain.
Chromium passes all four unchanged fluidness gates, while Firefox remains
26–28fps and fails them, despite correct native motion and rejoin.

Readonly light counts find17 point and19 spot sources; rendered contribution is
only one point slot initially and zero after rejoin. The existing eight-slot
capacity per type remains unchanged. The original image-error collector records
16 completed classifications per engine without dropped/unsettled requests:
per admission, one PNG network failure, three DDS and three TGA upstream HTTP
failures and one JPG origin refusal. Those suffixes are observations, not decoded
format or decoder-cause evidence. No admission widening, retries or substitute
assets are enabled. See the [actual source-bound cohort](evidence/hub-loaded-model-cohort-stock-20261002.json).
