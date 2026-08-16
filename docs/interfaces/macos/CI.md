# macOS continuous integration

The `macOS bootstrap` workflow is defined in
`.github/workflows/macos-bootstrap.yml`. It runs manually and on relevant pushes
to `apple-macos`.

The bootstrap defaults to an `x86_64` Intel runner. Manual dispatches may select
`target_arch=arm64`; that route builds Qt from source because the pinned aqt Qt
5 package is Intel-only. `arm_runner_size=standard` uses the available 7-GB
runner with dependency and compiler parallelism capped at two jobs. The
recommended `arm_runner_size=xlarge` route uses GitHub's M2 runner with 14 GB
RAM and GPU acceleration, but requires larger-runner billing to be enabled.
Every cache,
durable dependency checkpoint, compiler-object namespace and application
artifact includes the selected architecture, so ARM and Intel outputs cannot
be mixed. New namespace generations migrate from explicitly compatible prior complete caches before
falling back to a source build, then publish one exact current generation for
later runs. Build tools themselves are version-pinned and cached against the
runner's exact Python identity.

The Conan compatibility fingerprint hashes recipes, requirements, and only the
dependency-resolution prefix of `macos/build-macos.sh`. Changes confined to its
configure or compile functions therefore retain the verified package graph. A
one-time ordered v3 fallback migrates the earlier whole-script fingerprint; it
is removed by normal retention only after the new exact recovery layers exist.

Dependency resolution is divided into Qt, libnode/V8, and remaining-graph
stages. Qt is snapshotted before V8 begins; after libnode, both the Conan cache
and compiler cache are snapshotted again. Before the libnode Conan snapshot,
the completed packages are integrity-checked and their reproducible source,
build, and temporary trees are removed; the packaged libraries remain while a
multi-gigabyte V8 build tree cannot consume the shared Actions-cache quota.
The completed graph is integrity
checked, transient build directories are removed, and the integrity check is
repeated before the durable checkpoint is packaged. CMake configuration and
compilation are separate stages with independent build-tree checkpoints.
The remaining source-build stage has a 175-minute outer bound and a
165-minute supervisor bound. This accommodates a two-job ARM QtWebEngine build
while preserving a ten-minute CI cleanup window and the independent
15-minute inactivity detector.
The macOS source-Qt graph disables its unused PostgreSQL, MySQL, and ODBC
plugins. This keeps Qt independent of libpq 15.5, whose `strchrnul` fallback
cannot coexist safely with Xcode 16.4's macOS 15.5 SDK declarations while the
application still targets macOS 11. Failed dependency runs publish a partial
Conan generation, and that exact partial prefix is preferred over older stage
checkpoints on the next attempt. A one-time ARM migration prefix preserves the
completed libnode, Qt-stage, and dependency work from the pre-fix graph.

The evictable repository-wide Actions cache is only the fast path for Conan.
Its restore is capped at twelve minutes. A timeout or cache-service failure is
non-fatal: the workflow removes only the possibly partial `p` and `sources`
roots, then continues through the independently validated durable checkpoint.
This prevents an unavailable GitHub cache generation from consuming the whole
job or contaminating the artifact fallback.
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

Its per-object namespace fingerprints the compiler binary and version, Xcode
build, macOS SDK, architecture, build type, and deployment target. Source,
preprocessor output, and compile flags remain part of sccache's own object key,
so CMake-, Qt-recipe-, and monitoring-only edits do not strand compatible
objects in a new remote generation. The sccache server is stopped before either
a successful or failure snapshot. Complete
generations are preferred on restore, with partial failure generations as a
fallback. Only after the application has been uploaded does a branch- and
version-scoped pruner remove obsolete `sccache/*` objects; the current and one
previous verified generation remain. Expensive builds are not automatically
cancelled by a newer push.

The generated `build` tree is checkpointed separately after an orderly build
success or failure. All bootstrap runs configure one test-enabled CMake graph;
the dispatch input controls only whether the registered test targets are built
and executed. An exact source match is preferred; otherwise the newest tree
with the same compiler, Xcode, SDK, architecture, configuration, and dependency
inputs is restored and CMake incrementally rebuilds changed sources. During the
key migration, compatible test-enabled and client-only v2 trees remain ordered
fallbacks behind the shared v3 key, and every non-exact restored tree is
reconfigured with tests enabled. Once an exact complete v3 tree is available,
the workflow checks the restored cache's architecture, configuration,
deployment target, rendering
backend, release type, test-graph invariants, and the private exact-key marker
written into the completed tree before safely skipping the otherwise redundant
CMake generation pass. A missing or mismatched marker or invariant falls back
to normal configuration. This preserves
generated build state and objects in addition to sccache's content-addressed
compiler results. A GitHub-hosted runner remains ephemeral and cannot be kept
alive after a job, so caches and uploaded artifacts are the durable recovery
boundary.

The exact tree content hash covers CMake, client/library/plugin/native-test
sources, packaged scripts, the server-console graph, dependency
recipes, and the exact JSDoc, shader, and dylib-deployment inputs used by the
bundle. Runtime smokes, performance analyzers, watchdogs, telemetry, and
checkpoint implementations, Python/shell contract tests, and unpublished
developer content do not change the native graph or application bundle and
therefore do not invalidate an exact tree. A restored complete or partial tree
is not redundantly uploaded as a configured-only checkpoint, and the libnode
disk-sccache snapshot is saved only when validated statistics prove new local
compiler writes.

After a successful application upload, branch-local cache retention first
requires the exact current Ninja, Conan, and bounded disk-sccache generations to
be visible and nonempty through the GitHub API. Only then are older macOS
bootstrap generations for the same architecture and ref removed. The pruning
helper never selects iOS keys, another architecture/ref, or the remote
content-addressed `sccache/*` objects. If any current recovery layer cannot be
proven, it deletes nothing and fails the retention step.

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

Immediately after bundle verification and before runtime testing, it creates a
versioned external application manifest and a deterministic inner transport
archive, then uploads `overte-macos-<architecture>-<run-id>` with both
`build/application-archive/Overte.app.tar` and
`build/application-artifact/application-manifest.json`. The inner archive is
required because GitHub's artifact transport dereferences macOS framework and
QML symlinks; it preserves the original symlink topology and executable modes.
The manifest binds the
repository, bootstrap workflow path, ref, commit, run/attempt, target
architecture, Xcode/SDK, build configuration, deployment target, main
executable digest, and the digest plus architecture slices of every Mach-O in
the bundle. Every Mach-O must contain the requested target slice. Keeping the
manifest outside the bundle avoids a self-referential application hash. After
the runtime gates, the bootstrap also uploads:

- `overte-macos-smoke-<run-id>` with smoke diagnostics.

The diagnostic upload is retried once after a short bounded delay. A persistent
upload failure still fails the workflow so missing evidence cannot silently look
successful. The subsequent compiler-object and bootstrap-cache pruners are
best-effort cleanup: they fail closed before deleting anything when GitHub's
cache API is unavailable, but a transient cleanup outage does not turn an
otherwise fully tested application run red. A later successful run retries the
same branch-scoped retention policy.

The separate `.github/workflows/macos-runtime.yml` workflow restores one
explicit application artifact without rebuilding it. Before downloading, a
pinned GitHub API step requires a completed, successful bootstrap run from the
same repository and the exact `apple-macos` branch, then selects exactly one
live artifact with the expected run-scoped name. The runtime workflow safely
extracts the inner archive, requires the unique documented bundle/manifest
layout, and revalidates the complete manifest and Mach-O inventory. Unsafe
paths, escaping links, duplicate members, unsupported file types, and excessive
archive sizes fail closed before the bundle is used. The current runtime-test
checkout
may be newer than the application commit so script-only test improvements can
reuse an immutable build; the original application and source-run provenance
are copied into the runtime diagnostics result. It always runs startup
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

Performance artifacts contain only allowlisted hardware evidence. Raw
`system_profiler` output and `uname -a` are never written into the upload tree;
serial numbers, UUIDs, UDIDs, host names, NIC addresses, EDID data, and unknown
nested platform fields are discarded. The application writes its raw profile
result into a private temporary directory, and only the atomically sanitized
result is moved into the evidence tree. Runtime caches and generated profile
scripts containing absolute runner paths are excluded from the artifact.

GitHub currently reports `apple-macos` as unprotected. Enabling branch
protection or an equivalent repository ruleset remains recommended hardening,
but the runtime workflow does not require or attempt to change repository
settings. Until then, its trust boundary is the exact repository/head-repository
identity, workflow path, branch name, immutable commit SHA and run ID, successful
completion state, and unique live artifact checked above.

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
to `diagnostic-only`. The ARM build route is therefore useful for dependency,
architecture and native-code validation, but hosted results must not be used
for profile selection unless the probe itself reports `native-hardware`.

Qt WebEngine's Chromium checkout needs both its Conan source tree and a large
out-of-source build tree. On the ephemeral hosted ARM route the bootstrap
removes only allowlisted, non-macOS Xcode platforms, device support, and
simulator runtimes before restoring caches. The cleanup refuses local and
self-hosted machines, preserves the active MacOSX platform, logs disk space
before and after, and requires at least 50 GiB free after cache restore. This
prevents a late source-copy failure while leaving Conan recipe integrity and
the reusable Qt source checkpoint intact. Run `31925330624` established the
failure boundary: dependencies compiled for 49 minutes, then Qt's Chromium
source copy exhausted the final 11 GiB.

Probe run
[`31853662830`](https://github.com/noah-be/overte/actions/runs/31853662830)
completed natively on the standard `macos-15` arm64 runner, but CGL exposed no
usable pixel format (`pixel_format_count: 0`, error `10002`), created no
context, and reported no accelerated renderer. The runner is therefore
correctly classified as `diagnostic-only`. A native CPU architecture label is
not sufficient evidence of GPU access; graphics-profile certification requires
a physical or self-hosted Mac whose probe reports an accelerated OpenGL 4.1
context and a non-virtual renderer.

The monitoring contracts are exercised before dependency restore by
`macos/tests/source-contract-test.py` and
`macos/tests/conan-checkpoint-test.py`, with workflow integration covered by
`tests/workflow-contract-test.py`. The per-object remote store and safe pruning
policy are exercised by `macos/tests/sccache-remote-checkpoint-test.py`. The
suite also exercises the hosted-runner cleanup allowlist and its self-hosted
refusal, along with normal and signalled exit
codes, active long-running work, artificial inactivity, daemon-owned compiler
correlation, process-group cleanup, diagnostic redaction, live append behavior,
cache restore/save ordering, round-trip checkpoint recovery, corruption and
path-traversal rejection, candidate fallback, token redaction, and remote upload
digest validation.

For code-level platform regression coverage, every bootstrap configures all
registered C++/Qt CTest targets. The manual `run_native_tests` input controls
only their build and execution after the client and runtime gates, so ordinary
runs pay no test-target compile cost while reusing one compatible Ninja graph.
The native phase uses the same four-language compiler watchdog, runner
telemetry, process-group cleanup, and compiler-stall diagnostics as the
application build, then publishes CTest JUnit output. Conan and sccache remain
shared because their artifacts are content-addressed and
configuration-compatible.
