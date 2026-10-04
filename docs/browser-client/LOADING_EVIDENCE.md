<!-- SPDX-License-Identifier: Apache-2.0 -->

The subsequent approved compressed-color runtime cohort loaded all model tasks in
**23.784 seconds in Chromium** and **23.469 seconds in Firefox**, versus
30.072/28.941 seconds in the preceding progressive-geometry observations. These
are individual live public-world snapshots and the intervening cohort also
includes fixed-step movement and initial ground-support waiting; they are not
isolated causal or statistical speed guarantees. Each loaded293models, and
existing unsupported/missing assets remain. Actual native position/rejoin errors
were below0.8mm. Chromium passed all four fluid gates at about44.7FPS; Firefox
failed all four at about27.1FPS. Drawing buffers measured1280×800 versus2133×1333,
respectively; no resolution or acceptance threshold was lowered.

The actual connected-session color cache retained97/95compressed images within
its64MiB budget; GPU compressed uploads were observed. Firefox summed alpha
classification dropped from21.438s to4.825s (overlapping phases, not wall time).
Original-image diagnostics now record74unique Blob sources,76requests and just
2hits in each first session, establishing another real loading path to optimize.
The dataURL path was unused in this Hub cohort. The two audited KTX examples are
larger on the network than their original PNGs; no universal bandwidth claim is
made. See [runtime evidence](evidence/hub-loading-compressed-runtime-20261001.json).


The subsequent progressive-geometry cohort exposes actual detached model triangles
before textures finish. The short early input moved **0.545 m in Chromium** and
**0.633 m in Firefox**, versus zero before. Full model task readiness was
**30.072 / 28.941 seconds**; it was not faster than the preceding cache-only
cohort. Chromium passed four unchanged fluid gates; Firefox failed four at about
28.8 FPS. Both actual native pose comparisons and rejoin flows completed. This
proves earlier usable geometry, not complete textures or statistical speedup.
Source/dist coherence and all three owned runtime helper hashes passed. See the
last two runs in [the cohort evidence](evidence/hub-loading-render-cache-cohorts-20261001.json).

# World loading evidence

The latest isolated source-frozen cohorts on 2026-10-01 reached complete model
task readiness in **27.083 seconds in Chromium** and **27.321 seconds in Firefox**.
These are short muted/read-only Hub sessions, with the same application DPR cap
and unchanged fluidness thresholds. They do not mean every remote texture loaded:
failed source assets remain visible in the evidence. The original 42.125-second
Chromium baseline and these later runs differ in several reviewed loading fixes;
the overall observation is not attribution to one change or a statistical claim.

| Isolated cohort | Chromium readiness | Firefox readiness | Browser movement |
| --- | ---: | ---: | --- |
| Native draw state after alpha-worker yielding | 29.796 s | 31.380 s | Chromium four fluid gates pass; Firefox four fail |
| Prepared FBX cache and model scheduler | 27.083 s | 27.321 s | Chromium four fluid gates pass; Firefox four fail |

The prepared cache avoided 165/163 repeated FBX preparations respectively.
Chromium's cache retained 64 entries/9.86 MB; Firefox retained 64/11.24 MB, within
the unchanged per-world limits. Each model still owns its independent parsed
hierarchy and material samplers. Native movement disagreement stayed below
1.2 mm in both initial and rejoined cache sessions. Initial-world standing
samples measured approximately 50.7 FPS in Chromium and 28.6 FPS in Firefox;
Firefox still does not satisfy the required 30 FPS. Early movement remained
zero in both cohorts, motivating the separate real-geometry/support stage.

Exact source/build hashes, phases, safe request categories and all four gates
are in [the four cohort records](evidence/hub-loading-render-cache-cohorts-20261001.json).
The two earlier draw-state reports have empty runtime-helper hashes because the
observer searched `/tmp` while the managed gateway uses its own TMPDIR. The
cache observer now resolves that owned process's actual temporary root and
requires all three copied helper hashes, while retaining PID/start-tick checks.
This instrumentation gap is preserved in the earlier records.

Separately, two actual original Hub color images passed compressed-texture GPU
tests in stock Chromium 154 and Firefox 156: orientation, sRGB, alpha mask,
non-power-of-two mip levels and actual compressed uploads. Their KTX files are
larger than the PNGs (393,432/349,744 bytes versus 372,063/94,618), so there is
no demonstrated download-byte saving for these inputs. The standalone cache is
not yet wired into World or real domain authority. See
[the scoped GPU evidence](evidence/compressed-color-gpu-20261001.json).

The first isolated gateway optimization avoided 638 repeated upstream asset
loads in a real, read-only `overte_hub` session. Complete model loading improved
from 42.125 to 38.559 seconds, a 3.566-second (8.46%) reduction in one before/after
pair. This modest result does not establish a statistical speed guarantee or
complete the cold world and texture loading work.

Both runs used headed Chromium 154.0.8037.57 and the same NVIDIA GTX 1080 Ti WebGL
renderer. The browser production distribution and native protocol were unchanged;
only the gateway asset pipeline changed. Timing starts at actual browser
connection and ends at the first sampled state with no queued/loading models or
pending shader compilation. Measurements are sampled, not exact frame timestamps.

| Measurement | Before | Session cache only |
| --- | ---: | ---: |
| Session start (UTC, 2026-10-01) | 04:30:56.434 | 04:48:50.318 |
| Complete model readiness | 42.125 s | 38.559 s |
| Completed browser asset HTTP requests | 1,303 | 1,309 |
| Unique requested asset URL hashes | 664 | 665 |
| Repeated browser asset requests | 639 | 644 |
| Responses served from visitor memory | unavailable | 638 |
| Responses marked as upstream downloads | unavailable | 659 |
| Responses with unknown source | unavailable | 12 |

The cache reduces upstream network work while the browser still makes duplicate
HTTP requests. Browser responses remain `private, no-store`: every request checks
visitor ownership, configured origins and the current native permission revision.
The per-visitor byte cache is bounded to 128 MiB/256 entries with a 30-second reuse
window. Sixteen downloads run concurrently with bounded waiting readers; native
ATP callbacks keep their slots until they really finish. No global account or
credential cache was added.

After-run response lengths total 99,675,809 bytes. Before-run responses were
chunked without content length, so that byte count cannot be used for a before/after
bandwidth comparison. The same set of source asset addresses produced 17 HTTP 502
responses in each run; these failures were not counted as successful cache hits.
The baseline also recorded one cancelled request. Neither run edited public world
entities or enabled microphone input.

The fresh after-run gateway loaded server SHA-256
`e268d609756eb19d95034058db9d7c0ce13a4a7d9db8a7afc8ecaa6cbff69175`.
The gateway cohort passed 22 focused tests, including actual HTTP cancellation,
redirect validation, deduplication and the sixteen-download limit; the full
component suite passed 331 tests. These are tests of this cohort, not a claim that
subsequent browser optimization cohorts have already passed.

The native entity stream already yields after an 8 ms/64-record acquisition slice,
resumes after 16 ms, and publishes through the engine's 50 ms output timer. The
retained reports do not measure the first native snapshot precisely: their last
100 messages no longer include initial delivery. Early samples also show different
amounts of the genuinely streamed world. These observations do not justify
changing transport scheduling or admission deadlines.

Full FBX decode and alpha processing remain material costs. The after-run summed
FBX decode phases are about 25.37 seconds and texture alpha phases about 7.39
seconds; these sums include overlapping work and are not interchangeable with
wall-clock loading time. Browser image reuse and decoder work need separate cold
loading, texture correctness and movement measurements.

The two original reports retain only the browser's first 250 resource timing
entries, while their full asset counters contain 664/665 URL hashes. They therefore
cannot retrospectively provide complete FBX/image-category request totals.
The URL addresses still recoverable from those 250-entry buffers and recorded
failures identify 31 FBX URL hashes and 112 requests (81 repeats) in each run.
These are exact counts for that recoverable subset only, not full-world FBX
counts. Image-path subsets identify 50 hashes/53 requests/3 repeats before and
49 hashes/52 requests/3 repeats after. Unrecoverable hashes remain unclassified.

Future instrumentation records safe categories when each real request finishes,
plus start/end source hashes and an actual built JavaScript/CSS/WASM manifest.
No raw asset addresses or participant identifiers are published in the curated
[evidence before](evidence/hub-loading-before-session-cache.json) or
[evidence after](evidence/hub-loading-after-session-cache.json).

The next frontend cohort used an identical, start/end-coherent production manifest
in headed Chromium 154 and stock Firefox 156. Chromium's 05:14:29–05:16:39 UTC
journey passed all four unchanged fluidness gates: loaded-world standing, walking,
fresh-session standing and walking. Firefox's 05:21:19–05:23:57 UTC journey failed
all four. The requirement remains at least 30 FPS, frame p95 at most 66.7 ms and
no steady stall above 250 ms; no threshold was relaxed.

| Latest frontend cohort | Chromium | Firefox |
| --- | ---: | ---: |
| First sampled model readiness | 35.863 s | 42.485 s |
| Final initial-world standing FPS samples | 35.29 / 35.20 | 26.06 / 26.34 |
| Final initial-world standing frame p95 | 34.4 / 49.7 ms | 67 / 68 ms |
| Fresh-session walking FPS | 34.70 | 25.15 |
| Native movement disagreement, first / rejoin | 1.06 / 0.47 mm | 0.96 / 1.13 mm |
| Fluidness gates passed | 4 of 4 | 0 of 4 |

Both journeys loaded 297 models and exercised movement and reconnect with actual
native pose agreement. Those functional results do not erase Firefox's fluidness
failure. Their 1280×800 CSS viewports had different device pixel ratios:
Chromium emulated 1.0, while Firefox naturally used 1.667. The exact tested built
main caps renderer pixel ratio at **2**, so this is not a controlled equal-pixel
comparison. Firefox's masked GPU renderer label is retained as reported and is
not treated as independent identification of another physical GPU.

A read-only worker exploration may have overlapped part of the Chromium journey;
its exact interval was not captured. Its 35.863-second readiness sample is an
observation, not a controlled causal speed claim for the frontend changes.

The common built main is `assets/index-AsQJDvrj.js`, SHA-256
`c4e16ede2e0cc94b4d62cec1bd69c4818707bc86fd058479aece7cc4557596b7`.
The full [sanitized cohort report](evidence/hub-loading-browser-cohort-20261001.json)
records both manifests, source coherence, exact gates and bounded aggregates.
The user cancelled the 30-minute endurance requirement; these are short journeys.

Complete new category counts now come from every finished asset request, rather
than the first 250 resource timing entries. Chromium's **two-session** journey
made 590 FBX, 492 FST, 524 texture-metadata, 684 other JSON and 304 image requests.
These cover 122, 95, 133, 160 and 148 unique address hashes, respectively. They
must not be compared directly with the earlier single-session cache pair.
The integrated observer-only patch assigns private sessions public ordinals, checks
actual model readiness before accepting the unchanged 90-second loading deadline,
and records the observer/Firefox-driver source hashes. Cold texture loading and
fluid Firefox movement remain open acceptance work.

The alpha-worker-only Firefox follow-up used the same stock Firefox 156, natural
DPR 1.667 and CSS viewport as its previous run. The 05:40:43–05:42:55 UTC journey
reached sampled model readiness in 33.261 seconds versus 42.485 seconds: 9.224
seconds (21.71%) earlier in this single descriptive pair. The only common
production-source change is `texture-alpha-worker.ts`; its SHA-256 changed from
`19f26164f38e33946aa57e1fd0d3ce06da02b9ca2d24f3ca25f77f621aafd3a0` to
`68cc81f419ed2373cfe18e9efd950222452479a7a742c5e10b8d965264d91761`.
The updated main bundle is `assets/index-CUWSAQAC.js`, SHA-256
`d3476577aac85034d56246e764663249b99cd824d7ed6dab4f3b217a29caa491`.
Start/end source and distribution hashes remained coherent in each run.

The summed alpha phases changed from 843 calls/69.502 seconds/6.743-second maximum
to 845 calls/30.291 seconds/2.394-second maximum. These are measured phase durations
including overlapping waits, not pure CPU costs or complete loading wall time.
This result supports the loading improvement while leaving substantial stalls.
All four fluidness gates still **failed**: the last initial-world sample was
26.03 FPS with 68 ms frame p95. Actual walking and fresh-session reconnect retained
native pose agreement (3.63 mm first journey; 0.18 mm after reconnect), which does
not turn the failed fluidness result into completion.

The two reports' complete requested-target sets match: 670 URL hashes in each.
Their failed target/status multiplicities also match exactly: 34 HTTP 502s and
one HTTP 404 across two sessions, representing 16 distinct target hashes. No
source addresses are published. The observed ready-model counts nevertheless
change from 297 to 298; this streamed public world is not an immutable benchmark.

New observer metrics separate the latter flow into ordinals 1 and 2. Each makes
1,315 asset HTTP requests for 670 unique hashes (645 repeats), including 296 FBX,
247 FST, 264 texture-metadata, 343 other JSON and 152 image requests. Gateway
memory responses number 643 then 645; upstream-download responses number 655 then
653. Each session retains 17 unknown-source responses. These per-session totals
avoid mixing reconnect requests into cold-load counts. Exact gates, manifests,
phase counts and bounded aggregates are in the
[sanitized alpha-yield report](evidence/hub-loading-firefox-alpha-yield-20261001.json).
Cold texture completeness and fluid Firefox acceptance remain pending.
