# macOS development status

## Implemented

- client-only Conan 2 and CMake entry point;
- Intel Qt 5 and OpenGL 4.1 bootstrap strategy;
- local Qt and Node recipe repairs;
- serverless and online entity smoke scripts;
- CI bundle and diagnostic artifact definitions; and
- accepted `arm64` configuration value for future dependency work.

## Current evidence

The last documented CI attempt reached dependency position 36 before the Node
recipe failed because its generated makefiles received an unsupported build-type
name. The current branch contains a local mapping repair, but a successful
follow-up dependency, build, and runtime run has not been recorded.

## Open gates

1. Complete dependency resolution and CMake configuration.
2. Build and inspect `Overte.app` on current Xcode.
3. Launch and render the first frame.
4. Pass serverless, online, and transition smoke tests.
5. Validate native Apple Silicon dependencies and runtime.
6. Define signing, notarization, privacy, and packaging requirements.
