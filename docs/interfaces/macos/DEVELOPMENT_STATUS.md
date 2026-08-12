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
- accepted `arm64` configuration value for future dependency work.

## Current evidence

The Intel CI path now resolves dependencies, builds and bundles `Overte.app`,
passes its bundle-linkage gate, and passes the startup preflight. Runtime LLDB
evidence identified and removed two OpenGL loader failures: duplicated static
GLAD state across Mach-O images and an unconditional optional `GL_KHR_debug`
entry-point call. A fully monitored follow-up run must still prove the complete
serverless and online entity gates; those gates remain the definition of a
functional milestone.

## Open gates

1. Pass the serverless scene import, non-empty entity tree, render handoff, and
   snapshot gates in one monitored run.
2. Pass the online entity-server, query, data-receive, render-handoff, and
   snapshot gates.
3. Re-run serverless after online navigation to prove transition cleanup.
4. Validate native Apple Silicon dependencies and runtime.
5. Define signing, notarization, privacy, and packaging requirements.
