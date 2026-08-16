# macOS development status

## Implemented

- client-only Conan 2 and CMake entry point;
- Intel Qt 5 and OpenGL 4.1 bootstrap strategy;
- local Qt and Node recipe repairs;
- serverless and online entity smoke scripts;
- CI bundle and diagnostic artifact definitions;
- per-file compiler monitoring with CPU, memory, inactivity, signal, and stall
  diagnostics;
- deterministic complete and partial sccache recovery checkpoints;
- exact complete and failure-time partial build-tree checkpoints;
- five-second runner health sampling with sanitized 30-second live aggregates;
- shared GLAD state and optional OpenGL debug-entry-point guards;
- startup, bundle-linkage, and reusable runtime-only diagnostic workflows; and
- deterministic screenshot, frame-timing, JUnit, and repeated-runtime test
  harnesses;
- manifest-driven graphics profile and online-loading matrices that reject
  stale evidence, retain failed-attempt diagnostics, and cannot certify a
  software/virtual renderer as gameplay hardware;
- present, engine, batch, and GPU timing distributions alongside raw
  render-submit samples, without mutating the global resource-cache policy;
- a feature-complete local graphics fixture with procedural material and
  antialiasing targets, a post-warmup multi-present image gate, and immutable
  fixture/screenshot evidence binding;
- a stable allowlisted graphics-hardware identity that excludes application
  hashes and volatile or private platform inventory;
- allowlist-only performance artifacts that never persist raw hardware or
  network-interface identifiers;
- an external application provenance manifest that revalidates every Mach-O
  hash and architecture slice before runtime-only reuse;
- tested collidable-first Safe Landing resource priority and a cross-platform
  16-entity bound for unbudgeted renderable updates;
- an owning trace-output path that remains valid across the application event
  loop;
- same-process serverless-online-serverless transition acceptance with visual
  checks before, during, and after the domain visit;
- optional monitored build and JUnit execution of every registered native
  C++/Qt CTest; and
- opt-in native `arm64` bootstrap/runtime routing with source-built Qt,
  architecture-separated recovery caches and fail-closed Mach-O provenance.

## Current evidence

The Intel CI path resolves dependencies, builds and bundles `Overte.app`, and
passes bundle linkage and startup. Comprehensive run
[`31868069780`](https://github.com/noah-be/overte/actions/runs/31868069780)
passed every enabled gate: dependency and build checkpoint recovery, bundle
validation, startup, deterministic serverless rendering, public online entity
loading, graphics performance, and all 52 registered native C++/Qt tests. No
native test failed or was skipped.

The serverless scene produced its three named entities and a 1380x776 image
with 55,187 red and 30,216 cyan pixels. The online client captured 78 domain
entities, including 56 visible renderables, correlated an entity render
handoff, wrote a non-empty 1380x776 image, and exited normally. Neither runtime
needed timeout signals or produced a crash report. The informational
performance sample contained 31 frames with a 4.870 ms p95 and no sample above
16.67 ms.

Runtime-only run
[`31871253541`](https://github.com/noah-be/overte/actions/runs/31871253541)
reused that exact application bundle and passed startup, serverless and online
entity acceptance, the corrected deterministic performance smoke, the graphics
profile matrix, and the online-loading benchmark. The final 1380x776
performance image contained 55,187 red and 30,216 cyan fixture pixels; its 30
render-submit samples had a 4.663 ms p95. The matrix independently identified
the hosted Apple Software Renderer as GPU-bound: GPU/batch p95 was about 897 ms
and present p95 about 852 ms while engine p95 was about 8.96 ms. It therefore
correctly reported `diagnostic-only`, left `decision_ready` false, and selected
no gameplay profile.

Post-run audit found that the matrix case's own early screenshot contained only
the sky even though the separate performance-smoke image was valid. The current
matrix now takes distinct warmup and acceptance images, requires five seconds
and at least two further presents, verifies the red/cyan semantic layout, and
binds fixture features plus fixture and image hashes into the strict analyzer
schema. A hermetic sky-only image represents the failure as a negative
regression fixture. Runtime-only run
[`31878060076`](https://github.com/noah-be/overte/actions/runs/31878060076)
validated this hardened path: the final 1380x776 image contained 55,187 red and
30,216 cyan pixels after seven new presents, the independent re-analysis was
byte-for-byte equivalent, and the Software Renderer remained diagnostic-only
with no selected profile.

Native arm64 capability probe
[`31853662830`](https://github.com/noah-be/overte/actions/runs/31853662830)
also completed successfully as a test, but the standard M1 runner offered no
CGL pixel format or accelerated renderer. It therefore cannot execute the
graphics matrix or certify an Apple Silicon profile. The remaining native
profile gate explicitly requires a physical or self-hosted Apple-GPU runner.

The same runtime run produced the first clean post-startup cold/warm navigation
pair on that environment. Both processes reached 392 visible entities without
a crash: cold first-visible was 13.0 seconds and warm first-visible was 9.0
seconds. Packet receipt through decompression and tree mutation took less than
0.6 ms in each attempt, while domain-to-query took 4.16/1.68 seconds and
tree-to-render-handoff took 4.74/1.94 seconds. Ten active downloads and 33/34
pending downloads remained at the bounded observation endpoint, and the
software renderer did not sustain presentation or finish the screenshot/idle
gate. The analyzer consequently classified both attempts as
`render-present` plus `resource-backlog`, kept `measurement_passed` and
`decision_ready` false, and selected no concurrency. This single mutable public
world pair is diagnostic evidence only; the default concurrency intentionally
remains unchanged.

The current source adds navigation-scoped attribution inside the previously
dominant tree-to-render-handoff interval: queued add-slot delay, first pending
pass delay, first-domain-renderable handoff time, synchronous preload cost, add
pass count, adding-slot count, and incomplete-parent skips. The analyzer checks
that the three phase durations exactly reconstruct the original interval. This
instrumentation is behavior-neutral and requires the next application build
and runtime benchmark before an optimization is selected.

Earlier transition run
[`31778713708`](https://github.com/noah-be/overte/actions/runs/31778713708)
passed startup, the deterministic three-entity serverless scene, and the full
same-process serverless-online-serverless transition. It validated all three
PNG files and restored the red Box and cyan Sphere after returning from the
Hub. The process exited normally without timeout or termination signals.

Earlier stability run
[`31765778642`](https://github.com/noah-be/overte/actions/runs/31765778642)
passed deterministic performance collection and three consecutive
launch-render-quit stability cycles. Its informational baseline contained 31
frame samples with a 3.907 ms p95 and no sample above 16.67 ms; all three
stability iterations exited cleanly.

## Open gates

1. Run the full profile matrix three times on native, non-Rosetta Apple Silicon
   hardware; establish reviewed per-renderer image baselines before selecting a
   production quality profile.
2. Run online loading against a pinned, controlled domain for at least three
   cold/warm pairs before considering a download-concurrency or cache-policy
   change. The harness now binds such evidence to the expected domain UUID and
   a versioned sentinel entity; a public or unverified target cannot become
   decision-ready.
3. Validate native Apple Silicon dependencies and runtime.
4. Define signing, notarization, privacy, and packaging requirements.
