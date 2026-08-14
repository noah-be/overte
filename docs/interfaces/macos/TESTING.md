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

The serverless gate requires a populated entity tree and render handoff from the
deterministic three-entity fixture. It validates a 1380x776-or-larger PNG,
non-black content, opacity and contrast, red/cyan pixel populations, and their
expected left/right placement. The online gate additionally requires directory,
entity-server, query, receive, and render progress before accepting a non-empty
image. Immediately before capture it writes the complete nearby entity
inventory. A domain-hosted Box, Sphere, or Shape render-handoff UUID must occur
in that inventory, and the same inventory must contain at least one visible
primitive. The correlated protocol, tree, primitive-render, inventory, and
image gates prevent local helper entities or entity scripts from substituting
for an entity streamed by the domain's entity server. A passing process exit
without every marker and the correlated inventory is not acceptance. If the
software renderer writes the PNG but delays Qt's completion signal behind
domain-script startup, the script stops after a bounded 150-second settle;
the shell still requires and fully decodes the resulting image.

The hosted Intel runner exposes Apple's software OpenGL renderer. Compiling the
public Hub's complete model and text pipeline can take many minutes per shader,
even while the runner remains CPU-active. The smoke runner therefore passes the
explicit `--macosTestLightweightEntities` option together with its test script.
Only in that combination, scene submission is limited to Zones and primitive
Box, Sphere, and Shape entities. Network decoding, the complete entity tree,
inventory, and domain entity-script lifecycle remain active. The local avatar
and default client scripts are also suppressed; complex Web entities remain in
the inventory but never instantiate their WebEngine surface in this mode. Thus
unrelated local, model, text, and WebEngine pipelines cannot block the primitive
rendering proof. Normal application launches never enable this filter and
continue to submit the complete online scene. Consequently, this virtual-runner
gate proves online connectivity, entity streaming, primitive scene submission,
and visible OpenGL output; it does not replace full-scene model/Web validation
on a physical Mac.

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
shadow-casting directional light, two point lights, haze, bloom, PBR material,
fixed LOD, and a moving camera:

```bash
OVERTE_MACOS_PROFILE_MATRIX_MODE=quick \
OVERTE_MACOS_PROFILE_REPEATS=1 \
  macos/ci/performance-matrix.sh build/interface/Overte.app \
    build/macos-performance-matrix
```

Use `full` and three repeats for a profile decision on a physical Mac. Every
hardware profile first gets a throwaway warm-up process; measured processes are
then interleaved and their order is reversed on alternating repetitions to
reduce runner drift. The suite records raw render CPU samples, present/new-frame/drop
distributions, GPU/batch/engine time, draw calls, triangles, rendered items,
shadow work, texture/framebuffer memory, the exact requested and observed
settings, platform data, screenshots, traces, process diagnostics, Median, and
MAD. It compares Forward at 1/2/4 samples with balanced and maximum-quality
Deferred configurations.

Hardware classes never share results. The hosted paravirtualized/software-GL
runner is detected automatically and executes only a bounded `forward-compat`
diagnostic with 13 unlit local stress entities. This avoids presenting several
minutes of Apple software-driver shader compilation as gameplay performance;
the full lit/effect matrix is retained for physical hardware. Only a
shell-validated run gets a `profile-accepted` marker, and the aggregator rejects
incomplete or unaccepted measurements. On a physical Mac a selectable 60 Hz
profile must sustain at least 58 Hz present, 55 Hz new frames, and an 18 ms p95
render-submit time. The hosted renderer uses only a bounded diagnostic contract.
Its result is useful for shader, correctness, and regression diagnosis, but
cannot certify fluid gameplay or choose an Apple Silicon profile.

Online connectivity acceptance remains separate from loading performance. The
loading benchmark intentionally does **not** enable the lightweight entity
filter. It runs cold and immediately repeated warm processes against the same
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
the complete bounded queue time series, and host log milestones. Each pair uses
a new resource-cache directory for the cold process and reuses it for the warm
process. The driver-dependent GL program-binary cache is not covered by
`--cache`; this limitation is included in every aggregate. A mutable public
world is informational and never an absolute merge gate. A controlled,
versioned domain is required before adopting hard online-loading thresholds.

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

The manual `macOS bootstrap` input `run_native_tests` configures the application
with `OVERTE_BUILD_TESTS=ON`, builds every CTest-registered C++/Qt executable,
and runs CTest after the runtime gates. Compiler invocations retain the same
per-file watchdog and independent live log as the client build. The phase has
five-second host samples, 30-second aggregates, a 115-minute internal deadline,
a 120-minute step cap, a 15-minute limit per individual CTest, stall samples,
and an always-uploaded JUnit report. Set `OVERTE_TEST_TIMEOUT` to another
positive number of seconds for a deliberately longer test.

The native-test option gets a separate Ninja build-tree profile because its
generated graph differs from the client-only graph. It deliberately shares
Conan packages and content-addressed sccache objects with normal builds, so
enabling tests does not discard already compiled compatible code.

## Physical Mac matrix

Record the exact source revision, macOS version, Xcode version, architecture,
application hash, and result. Validate Intel first. Treat Apple Silicon as a
separate target and do not substitute a Rosetta result for a native `arm64`
build.
