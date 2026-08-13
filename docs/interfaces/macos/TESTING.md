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
image. A passing process exit without the expected markers is not acceptance.

## Performance and stability

An application built from the matching revision exposes `FrameTimings` only to
an explicit `--testScript`. Record the deterministic local scene with:

```bash
macos/ci/performance-smoke.sh build/interface/Overte.app build/macos-performance
```

The harness waits for a completed warm-up image, measures 20 seconds of moving
camera output, and stores raw microsecond samples plus mean, p50, p90, p95, p99,
maximum, 16.67/33.33 ms jank counts, and render/present/simulation rates. Its
validator recomputes every aggregate from the raw samples and publishes JSON
and JUnit. Results are informational by default. After baselines exist, set a
blocking threshold explicitly:

```bash
OVERTE_MACOS_PERFORMANCE_MAXIMUM_P95_MS=33.33 \
  macos/ci/performance-smoke.sh build/interface/Overte.app build/macos-performance
```

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
fixture image. This catches stale entity trees, stale network requests, and
mode-switch shutdown problems that independent launches cannot detect.

The manually dispatched `macOS runtime smoke` workflow can run performance,
three or five stability cycles, or the same-process transition against an
existing matching application artifact. This avoids rebuilding the app for
runtime-only test changes. A real
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
