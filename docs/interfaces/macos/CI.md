# macOS continuous integration

The `macOS bootstrap` workflow is defined in
`.github/workflows/macos-bootstrap.yml`. It runs manually and on relevant pushes
to `apple-macos`.

The `client-opengl-x86_64` job uses an Intel macOS runner, restores a Conan
cache, resolves dependencies, builds `Overte.app`, and runs the serverless and
online smoke gates.

On completion it uploads:

- `overte-macos-smoke-<run-id>` with smoke diagnostics;
- `overte-macos-x86_64-<run-id>` with `build/interface/Overte.app`.

Both artifacts are retained for seven days. The workflow does not verify a
distribution signature or notarization, so the application is a developer build
rather than a release. The workflow currently has no native Apple Silicon job.
