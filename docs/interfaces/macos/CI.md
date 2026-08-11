# macOS continuous integration

The `macOS bootstrap` workflow is defined in
`.github/workflows/macos-bootstrap.yml`. It runs manually and on relevant pushes
to `apple-macos`.

The `client-opengl-x86_64` job uses an Intel macOS runner, restores a Conan
cache, resolves dependencies, builds `Overte.app`, and runs the serverless and
online smoke gates.

Every C, C++, Objective-C, and Objective-C++ compilation is launched through
`macos/ci/compiler-watchdog.py`. The watchdog writes private append-only JSONL
records that are tailed independently of the CMake build output. Each record
identifies the source by basename and reports elapsed time, CPU activity, RSS,
and inactivity without retaining compiler arguments, environment variables, or
absolute paths. Active invocations report every 30 seconds. A compiler that has
neither consumed CPU nor changed its output for ten minutes is sampled and
terminated as a process group after a grace period.

The job uses a bounded `sccache` recovery cache. Its namespace fingerprints the
compiler binary and version, Xcode build, macOS SDK, architecture, build type,
deployment target, Qt source, and relevant repository inputs. The sccache
server is stopped before either a successful or failure snapshot. Complete
generations are preferred on restore, with partial failure generations as a
fallback. Expensive builds are not automatically cancelled by a newer push.

The aggregate build supervisor also writes a sanitized 30-second heartbeat to
the same live channel. Compiler activity can therefore be distinguished from a
compiler stall, while the absence of both compiler records and supervisor
heartbeats indicates a runner-level freeze. The build step is capped at 150
minutes and the complete job at 180 minutes.

On completion it uploads:

- `overte-macos-smoke-<run-id>` with smoke diagnostics;
- `overte-macos-x86_64-<run-id>` with `build/interface/Overte.app`.

Both artifacts are retained for seven days. The workflow does not verify a
distribution signature or notarization, so the application is a developer build
rather than a release. The workflow currently has no native Apple Silicon job.

The monitoring contracts are exercised before dependency restore by
`macos/tests/source-contract-test.py`. They include normal and signalled exit
codes, active long-running work, artificial inactivity, daemon-owned compiler
correlation, process-group cleanup, diagnostic redaction, live append behavior,
and cache restore/save ordering.
