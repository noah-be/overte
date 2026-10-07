# Bounded frame and texture-upload diagnostics

Material implementation assistance: OpenAI Codex.

The integrated diagnostic is disabled by default. It changes no graphics, simulation, collision, asset authority, worker settings or ordinary acceptance threshold. A source-coherent actual short stock Firefox156 Hub diagnostic now isolates97.6/98.3percent of idle synchronous task time in render submission. All four unchanged fluid gates fail; no speed improvement is claimed. [Actual evidence](evidence/hub-frame-cpu-upload-diagnostic-firefox-20261001.json).

The integrated source is World `57b74bc694...`, main `76b2ad8eb4...` and public Hub harness `981573b8c3...`. The parent verified both frozen proposal/followup manifests and every before/after byte hash before integration. All27diagnostic contracts and eight actual-function native rig contracts pass together. The production build passes. The existing six production cohorts precede this diagnostic and remain separately attributed.

`?cpuFrameTiming=1` captures the optional CPU observer at World creation. It records exclusive consecutive synchronous elapsed spans every eight existing RAF tasks: setup, physics/pose callback, avatar/camera, local-light selection, render submission (including its original metric bookkeeping), diagnostic/scheduling remainder. Empty scenes, model loading, modelJobsIdle and paused presentation remain separate fixed populations. modelJobsIdle means only that model-scheduler active/queued jobs and compilingGraphics are zero in a nonempty scene; Image/Material work can still be pending. It is not full world or texture readiness. These are JavaScript-thread wall spans, including driver waiting and preemption, not CPU cycles, async critical-path sums, compositor FPS or matched GPU subtraction. Its clock boundaries stay outside the existing graphicsSubmit/GPU CPU timer; the existing GPU observer remains independent.

The observer owns one opaque token, 2,048 sampled frames at most, 16,384 observed frames at most, fixed histogram bins and a 5-second valid-frame bound. It has no timer, WebGL calls, graph/material references or raw per-frame array. Failed or invalid frames are counted without publishing a false successful breakdown. Aborted owners, context loss and abandoned final tokens are cleared. Snapshot arrays are independent copies. Periodic work can alias systematic sampling; statistics describe the sampled population only. The owner is the World lifetime, not an individual permission revision. Transient reconnects that retain the same World aggregate into that owner; leaving/new joins allocate a fresh owner. No visitor/domain identifiers or object references are retained.

The ordinary production entry has the option off unless its explicit URL query is enabled. The harness can request it with `OVERTE_LAB_CPU_FRAME_TIMING=1`. Independent `OVERTE_LAB_UPLOAD_PROFILE=1` adds a bounded histogram around the harness's already existing upload wrappers. It distinguishes all seven native DOM source kinds, typed-data, null-data and numeric PBO arguments, dimensions, mip, type/format and phase. Exact bounded argument signatures and scalar fields are checked; unknown signatures retain elapsed-call accounting with null dimensions/format/type and a separate counter. It never issues a GL query or reads source URLs. Weak identities do not retain images; their counts are capped lower bounds, not texture/GPU residency. Caps are one million records, 1,024 weak sources and 128 histogram buckets per each of six phases. Without that flag, no new phase-setting browser round trip is added.

Existing `OVERTE_LAB_PROFILE=1` still applies only to Chromium. The harness additionally preserves a timestamped immutable raw-profile file and SHA/source/distribution/UTC attribution while retaining its old ignored latest-file alias. Raw profile contents are private local artifacts. Only curated numeric/hash aggregates belong in portable evidence; raw profiles and resource/event records remain private.

Verify from `browser-client`:

```sh
node --import tsx src/world-cpu-frame-timing.test.ts
node --import tsx src/world-cpu-segments.test.ts
node tests/integration/hub-upload-profile.test.mjs
node node_modules/typescript/bin/tsc --noEmit
node --check tests/integration/public-hub.mjs
```

Followup results: 9 observer contracts, 7 actual World method contracts and 11 upload/serialized-script contracts passed (27 CPU cases); TypeScript and harness syntax passed. The actual World tests exercise its original `animate` method with owned deterministic boundary clocks and a controlled renderer; they are not browser pixel or live-domain evidence. The actual diagnostic identifies renderer submission rather than static idle image uploads; internal traversal/draw/driver attribution still needs a separate measurement. Enabling a diagnostic is not a rendering optimization.


For an owned prepared gateway, request a short actual Firefox measurement:

```sh
OVERTE_LAB_URL=http://127.0.0.1:8090 OVERTE_LAB_BROWSER_DISPLAY=:0 \
  OVERTE_LAB_BROWSER=system-firefox OVERTE_LAB_RECONNECT=1 \
  OVERTE_LAB_REQUIRE_FLUID=1 OVERTE_LAB_CPU_FRAME_TIMING=1 \
  OVERTE_LAB_UPLOAD_PROFILE=1 node tests/integration/public-hub.mjs
```

Run only one browser/GPU cohort at a time. The ordinary loading, native movement,
leave/rejoin and all four fluid gates remain enforced. No microphone or public
entity mutation is requested. Preserve failed cohorts and distinguish this
instrumented diagnostic from uninstrumented production performance evidence.
