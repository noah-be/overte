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
- same-process serverless-online-serverless transition acceptance with visual
  checks before, during, and after the domain visit;
- optional monitored build and JUnit execution of every registered native
  C++/Qt CTest; and
- accepted `arm64` configuration value for future dependency work.

## Current evidence

The Intel CI path resolves dependencies, builds and bundles `Overte.app`, and
passes bundle linkage and startup. Comprehensive run
[`31821239596`](https://github.com/noah-be/overte/actions/runs/31821239596)
passed every enabled gate on commit `e6f5d94a9e`: build and checkpoint recovery,
bundle validation, startup, deterministic serverless rendering, public online
entity loading, graphics performance, and all 50 registered native C++/Qt
tests. No native test failed or was skipped.

The serverless scene produced its three named entities and a 1380x776 image
with 55,187 red and 30,216 cyan pixels. The online client captured 78 domain
entities, including 56 visible renderables, correlated an entity render
handoff, wrote a non-empty 1380x776 image, and exited normally. Neither runtime
needed timeout signals or produced a crash report. The informational
performance sample contained 31 frames with a 4.870 ms p95 and no sample above
16.67 ms.

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

1. Establish stable performance baselines before making frame-time thresholds
   blocking.
2. Validate native Apple Silicon dependencies and runtime.
3. Define signing, notarization, privacy, and packaging requirements.
