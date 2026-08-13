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
- accepted `arm64` configuration value for future dependency work.

## Current evidence

The Intel CI path resolves dependencies, builds and bundles `Overte.app`, and
passes bundle linkage and startup. Run
[`31719242695`](https://github.com/noah-be/overte/actions/runs/31719242695)
then passed serverless and online acceptance in one monitored job. The local
fixture produced its three named entities and a 1380x776 image with 55,179 red
and 30,216 cyan pixels. The online client connected to the public Hub's domain
and entity server, sent its query, received entity data, handed entities to the
renderer, found eight nearby entities, saved a non-empty 1380x776 image, and
exited with status zero. Neither runtime needed timeout signals or produced a
crash report.

## Open gates

1. Pass the prepared same-process serverless-online-serverless transition gate
   on the Intel runtime artifact.
2. Establish stable performance baselines before making frame-time thresholds
   blocking.
3. Validate native Apple Silicon dependencies and runtime.
4. Define signing, notarization, privacy, and packaging requirements.
