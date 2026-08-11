# Fast-loading Overte worlds on Pico 4

This guide is based on repeatable measurements of `hifi://overte_hub/` on a
physical Pico 4. It is intentionally evidence-led: the numeric budgets below
are provisional until a larger cold- and warm-cache sample has been collected.

## Measure two different completion points

Do not treat disappearance of the loading screen as the end of loading.
Measure at least:

1. **Playable:** the complete initial entity sequence has arrived, Safe Landing
   has no blocking collision or visual entities, GPU uploads are stable, physics
   is enabled, and complete frames have been presented.
2. **Settled:** active and queued downloads and processing are zero, while asset
   request counts, entity packet counts, interface scripts, and entity-script
   preload counts remain unchanged for at least 10 seconds.

The Pico runner records both points plus a one-second time series:

```bash
./pico-world-loading-test.sh --runs 5
```

Tests require one Pico connected through wireless ADB. The runner refuses USB
ADB, acquires the repository-wide device lock, enforces display brightness 1%
and fan speed 100%, verifies both settings, then restores the prior brightness
and automatic fan control on every normal, error, or interrupted exit.

## Current overte_hub baseline

A three-run instrumented series reached the first playable frame in 39.3–50.7 s
(median 39.7 s), released the loading screen in 40.3–51.6 s (median 40.6 s),
and became settled in 71.8–93.8 s (median 89.3 s). Each run contained 921
tracked entities and three or four domain/entity-stream resets. Cache state and
reconnections therefore need to be reported with every result; a single
headline duration is misleading.

The same series observed 1,179–1,215 HTTP requests, 87–102 MB over HTTP,
986–992 entity packets, and 283–288 entity-script load requests. Completed
entity-script preload callbacks reached 196–198. An earlier run also observed
about 20 MB over ATP. These are observations, not recommended limits.

## World-authoring priorities

- Make spawn-area collision geometry available first. Safe Landing deliberately
  holds physics and the opaque loading screen while nearby collision or visual
  entities are incomplete.
- Reduce initial request fan-out. Bundle related assets where practical, reuse
  URLs, and avoid assigning unique textures or materials to many small entities.
- Keep spawn assets small. Use mobile-sized textures, compressed texture paths
  supported by the client, low-complexity meshes, and simple collision hulls.
- Defer entities outside the initial view/distance and optional decoration until
  after the player is safely present. Validate this with entity-packet counters,
  not only by looking at the screen.
- Avoid starting hundreds of entity scripts simultaneously. Load essential
  interaction scripts first, defer optional behavior, and keep `preload()` short
  and non-blocking.
- Do not make the initial scene depend on a long chain of script-triggered entity
  creation. Such work occurs after the initial entity sequence and can make a
  world appear ready while it is still changing substantially.
- Test cold and warm caches separately, and record domain resets. A reconnection
  can dominate the result even when local asset processing is fast.

## Telemetry definitions

The milestone CSV records domain connection, first world data, entity-sequence
completion, Safe Landing completion, GPU readiness, physics activation, first
playable frame, loading-screen release, post-load quiet time, entity counts,
recovery attempts, presented frames, and domain resets.

The companion `-samples.csv` records active/pending downloads, processing
queues, ATP and HTTP request/byte counters, entity packets/bytes, running
interface scripts, GPU memory, Safe Landing blockers and sequence state,
entity-script loads and completed preloads, and active script/model/texture/
audio/other resources. Use this series to find what loaded after the screen,
rather than inferring it from the final duration.

The companion `-active-resources.csv` adds one row for every resource that was
active at a sample: category, progress, received/total bytes, and a
percent-encoded URL. Group rows by URL and compare the first and last elapsed
sample to identify resources that remain active across the loading-screen
release. `qrc:` entries are client-bundled assets; network URLs identify world
content or scripts.

In one active-resource validation, the longest-lived observed request was the
model `.../Misc/woodypillow/bodypillow3.fbx` at 6.4 s across samples. A repeat
run did not reproduce that long request, so it remains only a candidate for
inspection, not a proven bottleneck.

The repeat run exposed a more consistent post-screen cost: entity-script
preload callbacks increased from 6 to 198 between roughly 15.5 s and 85 s,
while download queues were often already empty. World authors should therefore
measure and reduce deferred script/preload work independently of network
requests.

The slow-preload diagnostic run identified repeated `sitClient.js` preload
calls taking 0.5–4.3 s. The same run kept `birds-nest.fbx` active for 25.4 s
and `coffee_table.glb` for 23.0 s. These are concrete candidates for
deduplication, deferral, mesh simplification, or replacement in the initial
spawn area. That run also had an 18.8 s maximum telemetry gap, so these local
operations materially affect perceived loading even while rendering continues.

For a compact human-readable summary, run:

```bash
./pico-world-loading-report.sh power-results/<run>.csv
```

The report includes milestone ranges, HTTP/entity/script deltas, category
counts, and the longest-lived active resources.

The runner additionally writes `*-diagnostics.log`, containing filtered
slow-preload and per-stage update logs for each run.

The report ends with provisional `HIGH` priorities for interface telemetry gaps
of at least 10 s, cumulative script-preload cost of at least 10 s per URL, and
active-resource spans of at least 10 s. These thresholds are triage aids, not
hard platform limits; confirm any proposed world change with a new series.
When the server advertises a resource size, the report also lists the largest
active `bytes_total` values; unknown sizes are intentionally not estimated.

## Latest diagnostic run

The latest complete run reached a playable frame at 43.8 s, released the
loading screen at 44.7 s, and became quiet at 69.2 s. It recorded 1,174 HTTP
requests, 86.4 MB of HTTP data, 982 entity packets, 293 entity-script loads,
and 196 completed preload callbacks. The largest telemetry gap was 13.5 s.

The diagnostics log reported one `sitClient.js` preload taking 10.2 s and an
active `Lamp_Stand.glb` request spanning 25.9 s. These timings make repeated
client-side script preload work and large model dependencies first-class
optimization targets for the world author; they are not hidden by the loading
screen milestone.

The report aggregates these calls as well: in this run `sitClient.js` accounted
for four slow preload calls and 14.2 s of cumulative preload time. When the
same URL is attached to many entities, inspect whether all instances need to be
in the initial scene and whether the script can avoid expensive work in every
entity's `preload()` method.

## Live VM A/B and ten-second Pico target

For a reproducible live comparison, a fresh Proxmox VM was used as the private
test server. Replace `(Proxmox Overte VM IP)` below with the VM's LAN address.
For installation and server setup, follow the [official Overte Linux domain
server documentation](https://docs.overte.org/en/latest/host/server-setup/linux-server.html).
The VM was given isolated Overte instances: original (`40202`), conservative optimized
(`40302`), aggressive (`40402`), and ultra (`40502`). The Pico reached the Hub
coordinates at `155.084,-98.5,-397.328` over WLAN ADB, with brightness 1% and
fan 100% enforced for every run. The local domain has no public place name, so
the validation uses the connection flag and world ID instead.

The ultra fixture (`overte-hub-pico4-ultra.json`) removes the measured
`waves3600.fbx` startup model and external HDR skybox/ambient URLs from the two
spawn-area zones, while retaining the rest of the Hub geometry. A five-run cold
series on the physical Pico after the final loading-handoff fix produced:

| milestone | runs | median | range |
|---|---:|---:|---:|
| loading-screen release | 5 | **8.64 s** | 8.51–10.07 s |
| settled (10 s quiet) | 5 | 39.6 s | 36.7–49.9 s |

All five runs connected and completed the entity sequence; the first run's
10.07 s release is the only target miss. The remaining settled phase is mostly
post-screen resource/processing work and must not be hidden by shortening the
loading overlay. The original VM five-run baseline released at a median 12.32 s
and settled at 37.7 s, so the ultra fixture trades a small amount of post-load
settling variance for a 3.7 s faster visible handoff.

The final Pico handoff keeps a 30-presented-frame gate, ignores stale
safe-landing timestamps from the local startup scene, and uses a 1.0 s scene
settle plus 0.1 s READY display with bounded timeouts. This is safe only because
physics and GPU readiness are already established; do not copy the constants to
desktop clients without the same milestone gates.

The Pico application in this private test setup uses this ultra domain as its
ordinary startup target,
so launching the app without an explicit deep link enters the optimized world
automatically. The deployed LAN endpoint is
`hifi://(Proxmox Overte VM IP):40502/155.084,-98.5,-397.328`; replace the
placeholder in a local build before deploying. Explicit command-line URLs remain
available for diagnostics.

Inspection of the measured `sitClient.js` source explains why: every
`preload()` immediately starts 13 presit-image `TextureCache.prefetch()` calls,
reads entity `userData`, and calls `requestSitData()`. For a Pico-optimized
world, use a shared image/resource cache, defer presit image prefetching until
the player approaches or interacts with a seat, and avoid a per-entity network
request during initial world construction. This is a concrete authoring change
that can be validated by rerunning the same telemetry and comparing preload
totals and `max_sample_gap`.

## Five-run diagnostics series

A five-run series with brightness 1% and fan 100% completed all runs. The median
playable time was 40.9 s, median loading-screen release 41.9 s, and median
settled time 94.3 s. Median maximum telemetry gap was 20.7 s, showing that
post-screen local work remains substantial even when the render thread stays
active.

Across the five diagnostics logs, `sitClient.js` produced 144 slow preload
calls totaling 157.2 s, while `script_server_crasher_client_console.js`
produced five calls totaling 42.5 s. These totals are cumulative across
entities and runs; they are not a single wall-clock duration, but they clearly
rank repeated entity scripts ahead of ordinary one-off assets for optimization.

The second script is explicitly a diagnostic/crasher control. Its `preload()`
calls a remote `Script.require()` for a tactile UI library and constructs a
renderer for every instance. It should not be present in a production Pico
spawn area; remove debug/crasher controls from the initial entity set or defer
them behind an explicit developer-only interaction.

Across the same five runs, 191–197 of the 198 preload callbacks occurred after
the loading screen had already been released. The remaining post-release quiet
window was still about 50–55 s per run. This confirms that the screen milestone
and the settled-world milestone measure different user-visible phases and that
initial script fan-out is the dominant post-screen work to reduce.

It also reports `max_sample_gap`. A large value means the interface update loop
did not publish telemetry during that interval; treat it as a real local stall,
even if the render thread continued displaying frames. In the repeat validation
the maximum gap was 19.1 s, coinciding with deferred entity-script preload work.

## Before publishing a performance claim

Use at least five runs for each cache condition. Report median and worst case,
the number of domain resets, playable time, loading-screen release time, settled
time, resource bytes and request counts, entity count, and script-load count.
Discard a run only for a documented infrastructure failure; a slow reconnect is
part of the user experience and must remain in the data.

## Serverless Hub A/B fixture

The branch also contains an exported Hub fixture in
`android/vr/pico/world-copies/overte-hub-original.json` and a conservative optimized
copy in `android/vr/pico/world-copies/overte-hub-pico4-optimized.json`. Both are bundled
under `file:///~/serverless/` for repeatable Pico tests. The optimized copy
removes the 14 measured `sitClient.js` entity scripts while preserving entity
geometry, transforms, and IDs.

Three matched runs per fixture were executed with brightness 1% and fan 100%.
The serverless loader does not emit a domain entity-sequence milestone, so its
`entity_sequence_complete_ms` is `-1`; the runner's `--serverless` mode checks
the remaining milestones and accepts the local-loader status explicitly.

| fixture | median playable | median release | median settled |
|---|---:|---:|---:|
| original | 35.7 s | 36.8 s | 61.0 s |
| optimized | 39.0 s | 39.9 s | 65.9 s |

In this small serverless series the optimized copy was not faster (about +3.4 s
playable and +4.9 s settled). The result is therefore a negative/neutral A/B
finding, not evidence to remove the change from a live Hub: entity scripts were
outside the measured spawn/culling volume in this fixture (`tracked_entities=0`)
and the series is only three runs. Use the copy as a reproducible harness, then
repeat at the actual spawn position after moving the relevant seating entities
into the initial visible volume. The original and optimized CSV, samples,
active-resource snapshots, and diagnostics remain in `power-results/` locally;
that directory is intentionally ignored by Git.

The serverless loader does not execute the exported remote entity scripts in
this fixture, so its script-preload counters remain zero. The live Hub series is
the authoritative measurement for `sitClient.js`; the serverless copies are
useful for geometry/resource and packaging checks. Run
`tests/serverless-hub-fixture-test.sh` to verify schema, entity-ID parity, and
the expected 14-script removal after editing either copy.

## Follow-up live Hub baseline

After fixing the runner's early-status race, a fresh five-run live Hub series
completed successfully with 923 tracked entities on every run. Medians were
39.5 s to playable, 40.4 s to loading-screen release, and 95.3 s to settled.
Median traffic was 1,206 HTTP requests and 100.7 MB; the median maximum
telemetry gap was 20.6 s.

The priority ordering is stable and stronger than the earlier sample: the
`sitClient.js` URL accounted for 126 preload calls and 109.7 s cumulative time,
while `script_server_crasher_client_console.js?2` accounted for five calls and
60.8 s. The longest active resource was `waves3600.fbx` at 30.9 s; the largest
advertised resource was `SKY-HDR-sunset_fairway_2k.exr` at 4.93 MB. These are
the first production-world changes to validate: remove/defer the crasher
control, and replace per-seat startup prefetch/network work with shared,
interaction-triggered loading before touching lower-impact assets.
