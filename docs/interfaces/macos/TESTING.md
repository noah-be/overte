# Test Overte for macOS

The macOS port has no VM-based acceptance path. Build and runtime evidence must
come from a Mac.

## Static and source contracts

```bash
python3 macos/tests/source-contract-test.py
bash -n macos/build-macos.sh macos/ci/*.sh
```

These checks do not prove that the application links, launches, or renders.

## Runtime smoke tests

After `Overte.app` builds, CI and local developers can run:

```bash
macos/ci/serverless-smoke.sh build/interface/Overte.app build/macos-smoke
macos/ci/online-smoke.sh build/interface/Overte.app build/macos-online-smoke
```

The serverless gate opens a deterministic three-entity URL through the normal
application path. It does not override render preferences, camera state,
avatar visibility, default scripts, or scene visibility. The fixture names
alone are not readiness: the import must be committed, all three entities must
remain present, and at least two new display presents plus a five-second stable
interval must complete before the single evidence image is requested. The PNG
check proves that both colored fixture entities reached the normal final frame.

The online gate likewise leaves the complete production scene untouched. It
requires directory, entity-server, query, receive, entity-tree, and render
progress, at least one loaded visible model, idle resource queues, completed texture loads,
a stable interval, and a newer presented frame. Immediately before capture it
writes the complete nearby entity inventory. The script writes its controlled
completion sentinel only after Qt reports a nonempty saved-snapshot path. A
pending or failed callback never becomes success evidence; the outer supervisor
captures a macOS thread sample on a timeout and the shell fails closed.

The hosted Intel runner exposes Apple's software OpenGL renderer, but the smoke
tests do not compensate by filtering entities or lowering graphics settings.
Slow or failed full-scene rendering is treated as an application defect. The
same rule applies to the optional serverless-online-serverless transition: it
navigates between known URLs while retaining production scripts, avatar,
camera, entity scene, materials, and renderer preferences.

## Performance and stability

An application built from the matching revision exposes `FrameTimings` only to
an explicit `--testScript`. Record the deterministic local scene with:

```bash
macos/ci/performance-smoke.sh build/interface/Overte.app build/macos-performance
```

The harness waits for a completed warm-up image, then measures moving-camera
output for at least 20 seconds and until it has 30 complete render samples. A
90-second ceiling bounds abnormally slow runs. It stores raw microsecond samples
plus mean, p50, p90, p95, p99, maximum, 16.67/33.33 ms jank counts, and
render/present/simulation rates. Its validator recomputes every aggregate from
the raw samples and publishes JSON and JUnit. Results are informational by
default. After baselines exist, set a blocking threshold explicitly:

```bash
OVERTE_MACOS_PERFORMANCE_MAXIMUM_P95_MS=33.33 \
  macos/ci/performance-smoke.sh build/interface/Overte.app build/macos-performance
```

The single-profile smoke is only a fast regression signal. It deliberately
uses unlit primitives and cannot choose a production quality profile. The
profiling matrix exercises a deterministic local scene with 45 lit shapes, a
shadow-casting directional light, two point lights, haze, bloom, PBR and local
procedural materials, an explicit antialiasing edge target, fixed LOD, and a
moving camera:

```bash
OVERTE_MACOS_PROFILE_MATRIX_MODE=quick \
OVERTE_MACOS_PROFILE_REPEATS=1 \
  macos/ci/performance-matrix.sh build/interface/Overte.app \
    build/macos-performance-matrix
```

Use `full` and three repeats for a profile decision on a physical Mac. A quick
matrix or a one-run matrix can only report a provisional profile and never a
production selection. The full matrix has a 9,000-second supervised budget
inside a 160-minute workflow-step cap. This covers all five profile warm-ups
and fifteen measured processes at their individual bounded runtime while still
reserving ten minutes for orderly diagnostics and artifact upload. Every
hardware profile first gets a throwaway warm-up process; measured processes are
then interleaved and their order is reversed on alternating repetitions to
reduce runner drift. The suite records raw render CPU samples, present/new-frame/drop
distributions, GPU/batch/engine time, draw calls, triangles, rendered items,
shadow work, texture/framebuffer memory, the exact requested and observed
settings, platform data, screenshots, traces, process diagnostics, Median, and
MAD. It compares Forward at 1/2/4 samples with balanced and maximum-quality
Deferred configurations. The analyzer reconstructs the LOD timing summaries
from the raw 250-ms samples, rejects forged or inconsistent distributions, and
classifies each run as GPU-, CPU-engine-, CPU-submit-, present/pacing-, or
refresh-limited. The aggregate includes the dominant class and median p95 for
present, engine, batch, and GPU stages per profile. Each case first captures a
separate shader-warmup image, waits five seconds and at least two additional
display presents, and only then captures the acceptance image and starts the
measurement. The final image must contain the red fixture on the left and cyan
fixture on the right; a sky-only or prematurely captured frame fails even if
the generic nonblank-image checks pass.

Hardware classes never share results. The hosted paravirtualized/software-GL
runner is detected automatically and executes only a bounded `forward-compat`
diagnostic with 13 unlit local stress entities. This avoids presenting several
minutes of Apple software-driver shader compilation as gameplay performance;
the full lit/effect matrix is retained for physical hardware. Every invocation
is listed in an immutable attempt manifest. Only a shell-validated run gets a
`profile-accepted` marker, and the aggregator rejects missing, duplicate,
incomplete, unaccepted, or stale measurements. A failed throwaway
shader/resource warm-up also invalidates the decision. On a physical Mac every
one of the three runs of a selectable 60 Hz profile must sustain a present-rate
p10/p50 of at least 55/58 Hz, a new-frame-rate p10/p50 of at least 50/55 Hz,
dropped-frame p95 no greater than 0.5 Hz, render-submit p95/p99 no greater than
18/25 ms, and at most 0.5 percent of render-submit samples above 33.33 ms. A
profile must also be repeatable: at 60 Hz, repeat-to-repeat present/new-frame
MAD and spread may not exceed 2/6 Hz, render-submit p95 MAD/spread 2/6 ms, or
p99 MAD/spread 3/8 ms. The separate 30 Hz fallback uses 1.5/4 Hz, 4/10 ms, and
5/14 ms respectively and is only reported when no 60 Hz candidate exists; it is
never promoted to the selected gameplay profile. The analyzer binds every
result to the catalog fixture version and SHA-256, independently recorded
application SHA-256, the combined fixture/script SHA-256, the accepted image
SHA-256 and semantic validation result, the required fixture-feature list,
post-warmup present delta, exact requested and observed settings, expected
stress entity count, measurement duration, and internally recomputed
raw-sample statistics. Its stable hardware key is derived only from an
allowlisted architecture/model/GPU/renderer/display identity; application
hashes, network interfaces, extensions, serial data, and other volatile
platform blobs are excluded. The hosted renderer uses only a bounded diagnostic contract.
Its result is useful for shader, correctness, and regression diagnosis, but
cannot certify fluid gameplay or choose an Apple Silicon profile.

Before spending a full native build on GitHub's standard M1 runner, run the
Apple Silicon graphics capability probe:

```bash
gh workflow run macos-apple-silicon-probe.yml \
  -R noah-be/overte --ref apple-macos
```

The probe requires a native untranslated arm64 process, an accelerated CGL 4.1
pixel format, a created context, and a renderer name without software,
paravirtual, virtual, SwiftShader, llvmpipe, or softpipe markers. It uploads the
raw OpenGL and `system_profiler` evidence for fourteen days. GitHub documents
`macos-15` as a standard three-core M1 runner, but the repository deliberately
does not infer GPU suitability from that label alone.

The native application build and matching runtime restore are explicit manual
choices. The standard ARM route caps source-build parallelism at two jobs and
is suitable for architecture validation. Use the `xlarge` route for accelerated
Full/3 graphics profiling when larger-runner billing is available:

```bash
gh workflow run macos-bootstrap.yml -R noah-be/overte --ref apple-macos \
  -f target_arch=arm64 -f run_native_tests=true
gh workflow run macos-runtime.yml -R noah-be/overte --ref apple-macos \
  -f artifact_run_id=<successful-bootstrap-run> -f target_arch=arm64 \
  -f arm_runner_size=xlarge \
  -f profile_matrix_mode=full -f profile_repeats=3 -f run_online=false
```

The runtime workflow verifies the requested architecture against the external
application manifest and re-inventories every Mach-O before launch. An Intel
artifact cannot silently run under Rosetta in an ARM measurement. A Full/3 run
still remains diagnostic-only when CGL exposes software, paravirtual or no
renderer; only an accelerated physical Apple-GPU result is decision-ready.

Run [`31929316508`](https://github.com/noah-be/overte/actions/runs/31929316508)
is the current hosted diagnostic baseline for the hardened matrix contract. It
reused the normalized, provenance-bound application archive from successful
bootstrap run `31917486365`, passed bundle re-inventory, startup, and the
serverless smoke, and independently reproduced the checked-in analyzer result.
The matrix's final 1380x776 image contained 55,187 red and 30,216 cyan fixture
pixels after a distinct shader-warmup image, a five-second cooldown, and eight
additional presents after the fixture baseline. Fixture, image,
application, and hardware-identity hashes all matched, and the process exited
naturally with status zero in 128.767 seconds.
The Forward diagnostic remained unambiguously GPU-bound: GPU/batch p95 was
about 1011.3 ms, present p95 about 1091.5 ms, engine p95 about 6.74 ms, and
render-submit p95 37.506 ms. It retained 19 draw calls, 9,058 triangles, zero
dropped frames, and 12--60 pending texture transfers throughout the measured
window. The analyzer correctly reported the dominant class as `gpu`,
`diagnostic-only`, `decision_ready=false`, and no selected profile. This
prevents CPU submission or a valid image from being mistaken for fluid
gameplay. These approximately one-second GPU/present values characterize only
the Apple Software Renderer and are not an estimate of Apple Silicon hardware.
This run also exposed 12--60 MiB of pending GPU texture transfers throughout
the diagnostic window. Schema 4 therefore records exact download, processing,
and texture-transfer queue counts and requires every Full hardware run to
remain completely resource-idle for two continuous seconds before its warmup
snapshot. Diagnostic-lite continues without claiming that gate so a slow
software renderer remains useful for bounded diagnostics without contaminating
a native quality decision.
The earlier run `31871253541` exposed that the matrix's own early
profile screenshot could contain only the sky; a hermetic image with that
failure mode is now rejected by the regression suite.

Online connectivity acceptance remains separate from loading performance. The
loading benchmark also exercises the complete production entity scene without
a test-only entity filter. Its [navigation telemetry contract](ONLINE_LOADING_TELEMETRY.md)
defines the sanitized event state machine used by the analyzer. It runs cold
and immediately repeated warm processes against the same
isolated resource cache and can compare the desktop default with 16 concurrent
requests:

```bash
OVERTE_MACOS_ONLINE_CONCURRENCIES=10,16 \
OVERTE_MACOS_ONLINE_REPEATS=1 \
  macos/ci/online-loading-benchmark.sh build/interface/Overte.app \
    build/macos-online-loading
```

It records time to the first entity, first visible entity, completed captured
frame, five seconds of sustained zero download/processing/GPU-transfer queues,
the complete bounded queue time series, and navigation-scoped monotonic
milestones from URL acceptance through connection, query, packet receipt,
decode, tree mutation, render handoff, first present, and first visible output.
Legacy process-wide host markers remain troubleshooting data only. Each pair
uses a new resource-cache directory for the cold process and reuses it for the
warm process. The driver-dependent GL program-binary cache is not covered by
`--cache`; this limitation is included in every aggregate. Every planned
cold/warm attempt is manifest-driven, and partial metrics from crashes or
timeouts are retained instead of disappearing from the report. Stale result
directories are ignored. The aggregator computes peak and time-integrated
download/processing/texture pressure, post-visible present/new-frame rates, and
domain-to-entity-server-active, entity-server-active-to-query, query-to-data,
data-to-decode, decode-to-tree,
tree-to-handoff, handoff-to-present, and present-to-visible durations. Event
details from new app builds further split entity-server-active-to-query into
main-loop time until the first query attempt and guarded time until the query
is actually sent. Older evidence remains valid and reports this optional split
as unavailable.
records are accepted only for the run's validated navigation ID and sanitized
location digest; arbitrary fields, duplicate/out-of-order records, and missing
success milestones fail closed. It preserves the legacy end-to-end
classification, and separately classifies the largest measured phase before
first-visible (connection, query, stream, decode, tree mutation, render
handoff, first present, or visibility) and the post-visible health outcome
(render/present, screenshot completion, resource backlog, or no observed
bottleneck). This prevents a renderer that stops presenting after visibility
from hiding a much slower network/query phase in the loading path. On the hosted software renderer the suite
deliberately runs only the first requested concurrency, because two driver-pathological runs
cannot produce a meaningful download-concurrency comparison. Its script records
at most 70 seconds without visible content or 30 seconds after first-visible.
Before navigation it loads the deterministic local 3-entity fixture and waits
for complete fixture discovery, empty queues, and a new present. The test then
starts the sanitized navigation epoch and queues the online address lookup.
Core and script first-visible clocks must agree within 750 ms, so startup can
no longer contaminate world-loading durations. The 300-second outer bound
includes variable application startup and baseline settling; a private
completion-file checkpoint lets the supervisor stop the process group as soon
as the result is durable instead of waiting for the blocked renderer teardown.
The first validated visible frame is also saved immediately to the separate
`macos-online-loading-checkpoint.json`; that filename is deliberately not watched
by the completion supervisor. If a diagnostic process then exits on a signal,
the analyzer may consume that fail-closed checkpoint, or a completed LLDB retry,
only with matching navigation identity, digest, contiguous telemetry and paired
process/log evidence. The primary crash remains counted and incomplete. This
recovery path never applies to native-hardware acceptance or performance decisions.
The aggregate requires bounded connection/query evidence for both cold and warm
and first-visible evidence in at least one of them. If Apple's software GL
compiler prevents the screenshot/idle gates, it remains
`measurement_passed: false`, marks the cases skipped in JUnit, and reports
`diagnostic_observation_complete: true`; it never promotes that partial evidence
to a loading or gameplay decision. A mutable public world is informational and
never selects or changes the application default. A
controlled, versioned domain plus at least three complete native-hardware
repetitions is required before adopting hard online-loading thresholds.

In baseline run `31834975878`, cold c10/c16 reached first visible entities in
6.938/8.758 seconds but then crashed inside Apple's software OpenGL fragment
transform. Warm c10/c16 reached first visible entities in 66.942/15.281 seconds
but timed out while the presentation thread was actively compiling or executing
Apple software-renderer draw work. Public-server reconnects and different entity
counts made the two concurrency settings non-comparable, so the default remains
unchanged. These partial milestones and the native samples remain useful
bottleneck evidence even though no concurrency decision is permitted.

Run `31848707317` reproduced the limitation without a crash. Cold c10 reached
575 entities and first-visible at 4.974 seconds; warm c10 reached 580 entities
and first-visible at 12.752 seconds. The cold timeout sample spent every sample
of the Presentation Thread in Apple's native software-GL pipeline compiler.
Instrumented first-use draws took 121 seconds for `simple_forward` and 167
seconds for `sdf_text3D_forward`, after which a translucent Forward shader was
still compiling. Host telemetry remained CPU-active with ample RAM and disk.
This proves that the hosted full-world failure is a graphics-driver bottleneck,
not slow domain/entity discovery, cache loss, runner freeze, or resource
exhaustion.

Run `31851152345` validated the shorter diagnostic window and exposed two
independent result-handling cases. Warm c10 wrote a durable bounded result after
74.190 seconds with 580 entities and first-visible at 13.648 seconds, but the
outer supervisor later returned 124 because the software-renderer teardown did
not exit. Cold c10 connected and sent an entity query, then the mutable public
domain repeatedly disconnected before any EntityData arrived. This is why the
supervisor now stops on a fresh private completion checkpoint, while the
aggregator separately requires connection/query capture in both cache modes and
at least one first-visible observation. A missing result, an unobserved network
path, or a real process crash still fails closed.

Run `31852625900` validated the completion checkpoint end to end. Cold and warm
both wrote durable diagnostics and the supervisor stopped them without a wall
timeout or SIGKILL. Cold reached 580 entities and first-visible in 6.195 seconds;
warm reached 579 in 8.494 seconds and completed a screenshot in 11.889 seconds.
Cold domain-to-query/query-to-data/data-to-handoff phases were 5/1/2 seconds;
warm was 3/1/2 seconds. The cold post-visible present median was zero and 87.1%
of samples had no presentation; it ended with 34 pending downloads and 63 MB of
pending texture transfer. Warm captured a frame but ended with 172 pending
downloads and about 60 MB of texture transfer, while 86.9% of its post-visible
samples also had no presentation. The automated classifications are therefore
`render-present` for cold and `resource-backlog` for warm, with both signals
retained. This mutable-world pair does not support changing the default download
concurrency.

Run `31924286980` validated three diagnostic cold/warm repetitions with the
navigation epoch and detailed render-handoff attribution. One cold process
crashed with SIGSEGV; the remaining five exited normally, but none completed
both screenshot and sustained-idle gates. Octree decompression and tree
mutation were only 0.1--0.3 ms and synchronous preload work was at most 0.02 ms,
so neither is a measured bottleneck. Domain-to-query was 2.24--12.94 seconds
and was the dominant pre-visible phase in five of six attempts; render handoff
was 0.36--2.41 seconds when observed. After visibility, four attempts spent
more than 93% of samples at zero present rate, while every attempt retained a
resource backlog. The split classifier therefore reports
`entity-server-or-query` as the dominant first-visible latency bottleneck and
`render-present` as the dominant post-visible bottleneck for both cold and
warm. The diagnostic runner intentionally omitted c16, so this run still does
not justify changing download concurrency or production rendering defaults.

Public-world runs always remain informational, even on native hardware. A
concurrency or cache-policy decision requires runtime input
`online_loading_target_mode=controlled`, three repeats, a canonical expected
domain UUID, and a safe versioned sentinel entity name (for example
`overte-macos-benchmark-v1`). Every process must connect to that exact UUID and
find the sentinel after the local baseline entities disappear; this verified
state is persisted in both the first-visible checkpoint and final result. The
analyzer rejects mismatched UUIDs, missing sentinels, forged verification, and
public results claiming controlled identity. Only a complete native-hardware
controlled matrix may set `decision_ready` or `selected_concurrency`.

Repeated clean launch, local-scene render, screenshot, and shutdown cycles are
available with:

```bash
macos/ci/stability-smoke.sh build/interface/Overte.app build/macos-stability 3
```

Every cycle retains its own process, image, and log evidence. The summary and
JUnit report fail if any cycle times out, receives a termination signal, exits
non-zero, misses a runtime gate, or fails visual validation.

Same-process cleanup across both connection modes can be tested separately:

```bash
macos/ci/transition-smoke.sh build/interface/Overte.app build/macos-transition
```

It loads and captures the exact local fixture, connects to and captures the
public Hub only after the fixture entities disappear, returns to the local
scene, requires a second serverless import generation, and validates the final
fixture image. Both local phases restore the fixture's first-person camera pose
and use a completed warm-up frame plus a five-second render settle before their
validated captures. This catches stale entity trees, stale network requests,
camera state leaking across modes, and mode-switch shutdown problems that
independent launches cannot detect.

The manually dispatched `macOS runtime smoke` workflow can run performance,
the graphics profile matrix, cold/warm online loading, three or five stability
cycles, or the same-process transition against an existing matching
application artifact. This avoids rebuilding the app for runtime-only test
changes. A real
WindowServer/OpenGL context is required; Qt's offscreen platform is not a
substitute for the 3D graphics gates.

## Native code suite

The `macOS bootstrap` workflow always configures the application with
`OVERTE_BUILD_TESTS=ON`, keeping one reusable CMake/Ninja graph. Its manual
`run_native_tests` input only builds every CTest-registered C++/Qt executable
and runs CTest after the runtime gates. Compiler invocations retain the same
per-file watchdog and independent live log as the client build. The phase has
five-second host samples, 30-second aggregates, a 115-minute internal deadline,
a 120-minute step cap, a 15-minute limit per individual CTest, stall samples,
and an always-uploaded JUnit report. Set `OVERTE_TEST_TIMEOUT` to another
positive number of seconds for a deliberately longer test.

Normal runs still build only the `Overte` target and therefore do not compile
the optional test executables. Native-test runs share the same build-tree key,
Conan packages, and content-addressed sccache objects, so enabling test
execution does not discard already compiled compatible code.

## Physical Mac matrix

Record the exact source revision, macOS version, Xcode version, architecture,
application hash, and result. Validate Intel first. Treat Apple Silicon as a
separate target and do not substitute a Rosetta result for a native `arm64`
build.

For an Apple-Silicon profile decision, dispatch the runtime workflow with
`runtime_runner=apple-silicon-self-hosted`, `target_arch=arm64`, matrix mode
`full`, and three repeats. That choice resolves only to the fixed labels
`self-hosted`, `macOS`, `ARM64`, and
`overte-macos-apple-silicon-performance`; arbitrary runner labels are not
accepted. Before downloading or launching the application, the job requires a
native non-Rosetta process and compiles the repository CGL probe on that exact
machine. It fails closed unless the probe creates an accelerated OpenGL 4.1
context whose renderer is neither software nor virtualized. Hosted ARM remains
the diagnostic path and cannot certify a gameplay profile.
