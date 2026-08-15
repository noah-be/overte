# macOS continuous integration

The `macOS bootstrap` workflow is defined in
`.github/workflows/macos-bootstrap.yml`. It runs manually and on relevant pushes
to `apple-macos`.

The `client-opengl-x86_64` job uses an Intel macOS runner. The first hardened
generation intentionally uses new Conan, compiler, and build-tree namespaces,
so its initial run builds from source while creating the recovery state used by
later runs. Build tools themselves are version-pinned and cached against the
runner's exact Python identity.

Dependency resolution is divided into Qt, libnode/V8, and remaining-graph
stages. Qt is snapshotted before V8 begins; after libnode, both the Conan cache
and compiler cache are snapshotted again. The completed graph is integrity
checked, transient build directories are removed, and the integrity check is
repeated before the durable checkpoint is packaged. CMake configuration and
compilation are separate stages with independent build-tree checkpoints.

The evictable repository-wide Actions cache is only the fast path for Conan.
The workflow also publishes a complete Conan checkpoint as an immutable Actions
artifact immediately after successful dependency resolution. Its compatibility
name fingerprints the compiler, Xcode build, macOS SDK, architecture, build
configuration, deployment target, Qt source, recipe inputs, and relevant
toolchain inputs. A new runner probes the newest compatible, non-expired
artifact and uses it whenever the exact fast cache is unavailable.
Both the GitHub artifact's workflow-run metadata and the embedded manifest must
match the current repository id, head-repository id, and branch; a same-named
artifact from a fork or another branch is never eligible.

`macos/ci/conan-checkpoint.py` stores the `p` and `sources` roots as a logical
tar stream split into deterministic chunks of at most 384 MiB, alongside a
bounded JSON manifest. Before changing `CONAN_HOME`, restore validates the
format version, exact compatibility key, complete ordered chunk inventory,
individual and aggregate sizes and SHA-256 values, tar entry inventory, and all
archive/link paths. Invalid or incomplete newest candidates are
ignored in favor of an older valid compatible generation; if none is usable,
dependency resolution creates a replacement. The replacement upload is checked
against GitHub's artifact id, size, name, expiry state, and upload digest before
the job proceeds. Checkpoint artifacts use no compression pass over the already
mostly compressed dependency data and expire after 14 days, bounding storage
without sharing the Actions-cache LRU quota.
Because API metadata alone only proves GitHub's outer ZIP digest, the workflow
then downloads that exact uploaded artifact id and repeats the manifest, chunk,
aggregate, tar-inventory, and safe-path validation before continuing.

Every C, C++, Objective-C, and Objective-C++ compilation is launched through
`macos/ci/compiler-watchdog.py`. The watchdog writes private append-only JSONL
records that are tailed independently of the CMake build output. Each record
identifies the source by basename and reports elapsed time, CPU activity, RSS,
and inactivity without retaining compiler arguments, environment variables, or
absolute paths. Active invocations report every 30 seconds. A compiler that has
neither consumed CPU nor changed its output for ten minutes is sampled and
terminated as a process group after a grace period.

The job uses `sccache` v0.17.0 with a bounded 512 MiB disk layer and the GitHub
Actions remote backend. A real compilation probe must demonstrate a successful
remote write before any dependency build starts. Every successful cacheable
compiler invocation is therefore offered to the remote tier when the object
completes, not only when the whole Conan or client stage exits. The initial
probe fails closed on any remote error. Completed phases may report a degraded
remote tier only when the bounded disk tier proves that every cacheable miss
was captured without a local write failure; dependency packages are then
covered by the independently verified Conan artifact, and client objects by
the Ninja-tree checkpoint and uploaded application bundle.
The checked-in sccache configuration gives a newly started server up to 60
seconds to index a restored disk cache; the upstream ten-second default is too
short for a full 512 MiB generation on a fresh hosted runner.

Its namespace fingerprints the
compiler binary and version, Xcode build, macOS SDK, architecture, build type,
deployment target, Qt source, and relevant repository inputs. The sccache
server is stopped before either a successful or failure snapshot. Complete
generations are preferred on restore, with partial failure generations as a
fallback. Only after the application has been uploaded does a branch- and
version-scoped pruner remove obsolete `sccache/*` objects; the current and one
previous verified generation remain. Expensive builds are not automatically
cancelled by a newer push.

The generated `build` tree is checkpointed separately after an orderly build
success or failure. An exact source match is preferred; otherwise the newest
tree with the same compiler, Xcode, SDK, architecture, configuration, and
dependency inputs is restored and CMake incrementally rebuilds changed sources. This preserves
generated build state and objects in addition to sccache's content-addressed
compiler results. A GitHub-hosted runner remains ephemeral and cannot be kept
alive after a job, so caches and uploaded artifacts are the durable recovery
boundary.

The aggregate build supervisor also writes a sanitized 30-second heartbeat to
the same live channel. Compiler activity can therefore be distinguished from a
compiler stall, while the absence of both compiler records and supervisor
heartbeats indicates a runner-level freeze. Dependency restore, checkpoint
packaging, and checkpoint revalidation use the same resource supervisor. The
client build step is capped at 175 minutes and the complete job at 360 minutes.
Each supervised phase also has an earlier internal wall-clock limit. It records
diagnostics and terminates the whole process group before GitHub reaches its
outer step timeout, leaving enough time for failure checkpoints and diagnostic
uploads.

`macos/ci/runner-telemetry.py` samples host health every five seconds and emits
sanitized, flushed 30-second aggregates. It records CPU/load, RAM and memory
pressure, swap, free disk space, inode availability, process count, and bounded
five-minute build/Conan/sccache size samples. Threshold transitions are emitted
immediately. The telemetry supervisor preserves the supervised command's exit
status and never records commands, environment variables, paths, or secrets.

Immediately after bundle verification and before runtime testing, it uploads
`overte-macos-x86_64-<run-id>` with `build/interface/Overte.app`. After the
runtime gates, it also uploads:

- `overte-macos-smoke-<run-id>` with smoke diagnostics.

The separate `.github/workflows/macos-runtime.yml` workflow restores one
explicit application artifact without rebuilding it. It always runs startup
and serverless visual acceptance, optionally runs the public online world, and
can additionally record deterministic frame timings, compare five explicit
graphics-quality profiles, compare cold/warm full-world loading at controlled
download limits, or execute three/five launch-render-quit stability cycles.
The expensive matrix inputs default to off and reuse the exact uploaded app;
runtime-only test changes therefore need no rebuild. Independent optional
stages use `always()` plus the serverless prerequisite, so a graphics-matrix
failure cannot silently skip requested online-loading evidence. Results include raw
samples, screenshots, traces, host telemetry, machine-readable aggregates, and
JUnit XML. The graphics selector is hardware-keyed and accepts only runs that
completed process, image, and metrics validation. The hosted software renderer
automatically uses the small Forward diagnostic fixture; full lit/effect
profiles are reserved for physical Macs. Software-renderer results are
diagnostic only, and public-world loading is informational until a
versioned controlled domain exists.
The graphics aggregator independently recomputes frame quantiles, validates
every polled LOD timing row and render-stat distribution, and reports a dominant
GPU, CPU-engine, CPU-submit, present/pacing, or balanced bottleneck per profile.
Those classifications explain a result but do not weaken the 60 Hz selection
contract.

Both profiling suites create a new immutable plan manifest plus an append-only
attempt manifest and refuse non-empty output directories. Aggregators consume
only paths named by those manifests, so stale files cannot satisfy repetition
counts. A graphics decision additionally requires every planned profile, its
warm-up, three accepted native-hardware runs, exact app/profile hashes, exact
requested-versus-observed settings, consistent hardware/fixture identity, and
the per-run 60 Hz contract. A one-run matrix is provisional; 30 Hz is reported
only as a fallback. Online reports preserve partial metrics, timeout state, and
crash counts from failed attempts but never select a concurrency from a mutable
public world. A diagnostic software renderer runs only one cold/warm pair and
gives the test script 70 seconds to capture a bounded network observation or 30
seconds after first-visible. The process supervisor permits up to 210 seconds
for application startup, watches the private result file, and terminates the
software-renderer process group immediately after durable evidence is written.
A normal crash is still preserved as a failure; only supervisor-initiated
teardown after that checkpoint is accepted. The aggregate requires a domain
connection and entity query in both cache modes plus first-visible evidence in
at least one mode. Transient public-world failures remain explicit skipped
diagnostics rather than completed loading measurements. `measurement_passed`
remains false and no profile or concurrency can be selected from that evidence.
Each online attempt is also reduced to queue peaks and integrals, post-visible
present/new-frame behavior, connection-to-query/data/handoff phase durations,
and one explicit primary bottleneck. Cold and warm classifications stay separate
so a public-domain disconnect cannot be confused with an asset backlog or a
renderer that stopped presenting. Secondary signals are retained as counts, so
simultaneous present starvation and resource backlog are not collapsed into a
single label.

The application is retained for fourteen days and smoke diagnostics for seven
days. The workflow does not verify a
distribution signature or notarization, so the application is a developer build
rather than a release. Native Apple Silicon eligibility is probed separately by
`.github/workflows/macos-apple-silicon-probe.yml` on GitHub's standard
`macos-15` M1 runner. It compiles a minimal CGL 4.1 client and records the actual
GL renderer, context acceleration flag, architecture, and Rosetta state. Only
arm64, untranslated, accelerated, non-virtual renderer evidence is classified
as `native-hardware`; every missing or software/paravirtual result fails closed
to `diagnostic-only`. This small probe must pass before adding an arm64 app build
or using hosted results for profile selection.

The monitoring contracts are exercised before dependency restore by
`macos/tests/source-contract-test.py` and
`macos/tests/conan-checkpoint-test.py`, with workflow integration covered by
`tests/workflow-contract-test.py`. The per-object remote store and safe pruning
policy are exercised by `macos/tests/sccache-remote-checkpoint-test.py`. These
tests include normal and signalled exit
codes, active long-running work, artificial inactivity, daemon-owned compiler
correlation, process-group cleanup, diagnostic redaction, live append behavior,
cache restore/save ordering, round-trip checkpoint recovery, corruption and
path-traversal rejection, candidate fallback, token redaction, and remote upload
digest validation.

For code-level platform regression coverage, the manual bootstrap input
`run_native_tests` enables all registered C++/Qt CTest targets. The native phase
uses the same four-language compiler watchdog, runner telemetry, process-group
cleanup, and compiler-stall diagnostics as the application build, then publishes
CTest JUnit output. Test-enabled and client-only Ninja trees have distinct
profile keys; Conan and sccache remain shared because their artifacts are
content-addressed and configuration-compatible.
