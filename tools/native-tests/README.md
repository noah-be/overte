# Selective native C++ checks

The Linux native lane builds real Overte targets and runs selected Qt tests.
It complements the quick/host checks and device acceptance; it does not claim
Windows, Android, iOS, GPU, audio-device, or full user-journey qualification.

## Routing and cost boundaries

`repository-checks.yml` always calculates a route from the exact PR merge
candidate and its two event parents. Git's NUL-delimited, rename-disabled diff
includes additions, deletions, both sides of renames, and every file even in a
PR with more than 300 files. Missing/mismatched commits fail instead of silently
omitting native checks. Manual validation uses the broad route.
Routing checks out only policy files and reads the complete change inventory
from Git tree metadata. Trusted native tooling uses a sparse checkout; the actual
native build still checks out the complete candidate source.

| Change | Native work |
| --- | --- |
| Only known documentation, scripts, host-test paths, or an exact empty PR delta | No native job |
| Only `tests/shared` test sources/headers or native routing/runner Python | Small system-dependency build of the shared test component |
| Production C++ libraries or applications | Configure the product graph; build changed components and affected tests |
| Build/dependency definitions, unknown paths, non-regular files | Conservative product configuration and wider selection |

The full graph includes the Linux client, servers, native tools, and eligible
tests. Manual test applications and other platform toolchains remain separate.

Pure QML/JavaScript/UI/media content under `interface/resources` does not
trigger a native core build; host checks and device journeys own that behavior.
Changed QRC collections still require native resource-build validation. The
`full` route means the product build graph plus the eligible test manifest, not
every legacy test or the separate project runner's `full` profile.

CMake's file API supplies the configured target dependency graph. Every configured
C/C++ input is checked against routing exemptions; introducing compiled code under
a formerly host-only path requires updating the routing policy in the same change. Include-only
consumers also count, since a header dependency need not be a link dependency.
Library changes select dependent tests transitively. A single existing test
translation unit selects that executable; test headers and helpers select the
whole group. A removed/unmapped native component causes broad selection, even
when the same change also touches a known component. Non-regular file changes
force broad selection. Accompanying host/documentation files do not widen it.
Changed production targets and their affected link consumers are built even
where no native test covers them;
such cases also run the small shared regression set. This is compile and core
regression evidence, not newly invented behavioral coverage for that component.

The lane runs once per PR candidate, alongside host checks. There is no native
push trigger, OS matrix, automatic benchmark, or device provisioning. Superseded
PR runs are cancelled by the parent workflow. Checks do not repeat merely
when a tested draft becomes ready for review. The
`edited` trigger remains because changing the PR base needs fresh merge-candidate
validation; metadata edits can therefore rerun checks. Do not turn those runs
into successful skipped gates that could replace an earlier failed result.
Ordinary PR dependency resolution
uses `--build=never`: missing dependencies fail clearly instead of starting a
large hidden source build. Configuration/build/test failure fails the existing
`repository-checks` aggregate, including delegated synchronization PRs. An
intentional native skip is accepted only when the trusted route says `skip`.
Host qualification artifacts do not certify native results and cannot bypass
this additional gate.

The native job has a 45-minute ceiling, dependency resolution a 10-minute
ceiling, and each CTest program a 120-second ceiling. Build concurrency is two
on the GitHub runner. These are failure bounds, not measured performance goals.
Compiler objects (2 GiB ccache limit), generated shaders, and Conan dependencies are cached;
CMake configuration, target selection, and test results are always regenerated.
Compiler cache validity includes compiler and source/header contents. Dependency
cache identity includes the pinned image generation and dependency definitions.
The reviewed manual default-branch `Prepare native baseline` run seeds the compiler
cache for later PRs; caches written by one PR are not shared with other PRs.
Refresh the default-branch cache deliberately when hit rates deteriorate, without
adding a duplicate native build to every push.
Compiler caches are speed aids; a hit never substitutes for executing tests.
The shader cache is keyed from Ninja's declared shader inputs, the generated
command list, the actual commands, and shader compiler binary contents. It uses
exact matches only and is omitted when the selected targets do not need shaders.
After a hit, only generated output timestamps are refreshed to account for fresh
checkout timestamps. CMake/Ninja build state and source timestamps are not restored
or rewritten. Shader dependencies must remain complete in the build graph, as for
ordinary incremental builds. Qt resource metadata is fixed with
`QT_RCC_SOURCE_DATE_OVERRIDE=1` in this CI lane: otherwise identical resource
contents acquire new embedded timestamps and miss the compiler cache. Changed
resource contents still generate different code. This is build reuse, not reuse
of any test result.
The prepared Conan cache currently also supplies binaries missing from the
public remotes. Losing that cache is an infrastructure failure, not a passing
test or a reason to rebuild dependencies inside an ordinary PR. GitHub's
branch-scoped cache isolation prevents a PR cache from becoming a default-branch
cache. Do not change this to a privileged PR-target workflow.

## Selected tests and exclusions

[The manifest](../../.github/native-tests.json) lists each eligible executable,
optional Qt correctness methods, and exclusions with reasons. Normal developer
builds retain all existing tests. CI excludes benchmarks, internet fixtures,
hardware tests, and known placeholder suites. It must not label those exclusions
as passing coverage. Qt reports are retained; any reported skip, failure, empty
suite, or missing report fails the wrapper. Settings and caches are isolated per
executable.

`OVERTE_TEST_GROUPS` narrows native CMake configuration. `OVERTE_NATIVE_CI=ON`
selects the manifest and adds bounded CTest registrations. Outside CI these
options remain opt-in. Root build configuration and production library targets
are reused; there are no replacement/mock implementations of Overte libraries.

## Local execution

Use Ubuntu 24.04 with the pinned build image from `native-tests.yml`, or a host
with equivalent prerequisites. The core lane additionally needs `ccache`,
`libglm-dev`, and `nlohmann-json3-dev`. From the repository root:

```bash
bash tools/native-tests/configure.sh core
```

Use a fresh `build/native` directory when switching between core and full
toolchains, or set `OVERTE_NATIVE_BUILD_DIR` to a separate directory. Conan generation for the full lane also targets `build/native`, so
the existing shader-tool paths resolve in the actual CMake build directory.

For local focused work, build a concrete registered target and run its exact
CTest name, for example:

```bash
cmake --build build/native --target shared-AABoxTests --parallel 2
ctest --test-dir build/native -R '^shared-AABoxTests-test$' --output-on-failure --no-tests=error
```

The workflow's trusted planner writes `build/native-plan.json` bound to the
candidate SHA. `select.py` converts that plan and the configured CMake graph to
`build/native-selection.json`; `run.py` verifies the selected CTest inventory,
builds those targets, and writes timing/identity and JUnit results. Do not reuse
a plan or result from another candidate as merge evidence.

## Dependency preparation and activation

The first broad build requires prepared third-party binaries. The manual
`Prepare native baseline` workflow runs only on the default branch and
seeds the same dependency cache using `--build=missing`, then builds and tests
the product to seed reusable compiler objects. Prepared packages are saved before
product qualification, so a test failure does not discard expensive dependency
preparation. Its separate 180-minute budget is
explicit. Rerun after changing dependency definitions or the image generation. For a
reviewed dependency-update PR, provide its exact commit in `candidate_sha`;
otherwise the required new packages could not be prepared before merging that
PR. The workflow definition still comes from the default branch, checkout is
bound to this fork, and the tested baseline SHA is recorded. This manual input
is for reviewed code, not automatic execution of an arbitrary contributor ref.
The native lane uses `tools/native-tests/conan-linux.lock` to freeze resolved
recipe revisions, including transitive dependencies. Its contents also identify
the prepared dependency cache. This lock applies only to the Linux native lane;
it does not change other platform builds. When reviewing a dependency update,
regenerate the lock in the pinned image using the same profile and options:

```bash
conan lock create . -pr tools/conan-profiles/linux -s compiler.cppstd=gnu20 \
  -s build_type=Release -o 'Overte/*:qt_source=system' --build='*' --lockfile='' \
  --lockfile-out=tools/native-tests/conan-linux.lock
```

The lock command expands source-build requirements without compiling packages.
Review its diff and qualify the new packages before activating them. The lock
fixes recipe resolution; it does not promise identical system packages or
replace binary availability. Cache eviction or a
missing/new dependency must remain a visible prerequisite failure. Before relying
on this as an unattended long-term gate, distribute the qualified packages through
a durable fork-owned artifact or image store; GitHub cache retention is not a
package availability guarantee. That publication is outside local-only work.

Deploy in stages because selection and aggregation execute default-branch tools:

1. Integrate reviewed tools, test fixes, CMake support, manifest, and offline
   regressions before enabling new workflow callers. Keep trusted `native_required` false during this bootstrap; the new
   verifier then accepts the legacy workflow shape.
2. Prepare dependencies, then qualify the full native lane against the exact
   proposed source and pinned Linux environment. Confirm cold/warm build costs
   and all eligible tests. Do not activate an unqualified broad merge gate.
3. Integrate and propagate the workflow caller while the compatible trusted
   verifier is present. Finally set trusted `native_required` true (the desired
   state in this change) to reject every legacy workflow shape.
   Verify ordinary, docs-only, failed-native and sync PR cases. The existing
   `repository-checks` context is retained; no new ruleset context is needed.

Local source changes are not evidence that GitHub enforces this gate. Publishing,
cache preparation on GitHub, branch propagation, and live ruleset changes are
separate operations. Keep unavailable broad-build qualification explicit.

References: [GitHub required checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks),
[CMake file API](https://cmake.org/cmake/help/latest/manual/cmake-file-api.7.html),
[Conan lockfiles](https://docs.conan.io/2/tutorial/versioning/lockfiles.html),
[Qt resource timestamp handling](https://github.com/qt/qtbase/blob/5.15/src/tools/rcc/rcc.cpp),
[GitHub cache scope](https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows#restrictions-for-accessing-a-cache).
