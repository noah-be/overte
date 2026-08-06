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

Inspection of the measured `sitClient.js` source explains why: every
`preload()` immediately starts 13 presit-image `TextureCache.prefetch()` calls,
reads entity `userData`, and calls `requestSitData()`. For a Pico-optimized
world, use a shared image/resource cache, defer presit image prefetching until
the player approaches or interacts with a seat, and avoid a per-entity network
request during initial world construction. This is a concrete authoring change
that can be validated by rerunning the same telemetry and comparing preload
totals and `max_sample_gap`.

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
