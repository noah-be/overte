# Native CI qualification — 2026-09-27

The native lane is enforced for pull requests targeting `main` through the
existing required `repository-checks` result. It was activated by
[PR #983](https://github.com/noah-be/overte/pull/983), merged as
`4a01dc9f7ee60fe6304ab86f20d94008e317482b`, after the checks below passed.
Existing branch protections and required status contexts were retained.

## Scope and selection

The full Linux graph includes the client, servers, and tools: 98 build targets
and 32 CTest programs containing 148 Qt correctness functions in this revision.
All selected tests execute again even when compiler or shader caches are reused.
This is build and native correctness evidence; it does not qualify interactive
user journeys, physical devices, or other operating systems.

Routing compares the exact candidate with its verified event parents. Known
Markdown, host-script, QML, and media-only changes skip native work. Shared
test-only changes use the bounded core lane. Production C++ and build-definition
changes use the actual CMake dependency graph to select affected targets;
unknown native inputs require broad validation. Non-native repository checks
still apply according to their own scope.

## Measured full builds

Times below separate product compilation from test execution. Baseline work is
manual preparation, not a normal PR requirement. Runner variability and cache
retention mean these are observations, not latency guarantees.

| Run | Product build | Tests | Cache conditions |
| --- | ---: | ---: | --- |
| [Initial baseline](https://github.com/noah-be/overte/actions/runs/36269986693) | 4,101.700 s | 4.946 s | Cold product compilation; dependency preparation separately took 103 min 35 s |
| [First PR consumer](https://github.com/noah-be/overte/actions/runs/36280092282) | 2,698.721 s | 4.964 s | Partial compiler reuse; shader miss caused by different portable package paths |
| [Corrected baseline](https://github.com/noah-be/overte/actions/runs/36281406269) | 2,859.170 s | 4.976 s | Reused dependencies; seeded caches using the same portable layout as the image |
| [Qualified warm PR](https://github.com/noah-be/overte/actions/runs/36284395381) | 135.249 s | 5.028 s | 1,229/1,230 compiler hits and an exact shader-cache hit, both restored from `main` |

Every listed native run passed all 32 programs and 148 functions without skips.
The first PR run failed overall because of a host fixture telemetry race, fixed
and independently qualified in [PR #984](https://github.com/noah-be/overte/pull/984).
Its successful native job is not presented as a successful overall PR.

In the qualified warm run, the complete native job took 354 seconds, including
container setup, configuration, cache transfers, compilation, and tests. The
parallel host job took 356 seconds. Its suite passed 33 groups and all 340 selected
self-tests without skips (310.831 seconds of suite execution). Native work did
not extend that measured host-job duration. This observation applies to this
full candidate and does not promise identical timing for future changes.

The qualification removed only the initial diagnostic caches belonging to
`refs/pull/983/merge` before the final run. Restore logs bind both caches to the
corrected default-branch baseline, so this measures reuse available to another
PR rather than a repeat relying on its own previous cache. Compiler statistics
are reset after restoration to avoid counting inherited calls.

## Focused selection and merge-gate rejection

[PR #985](https://github.com/noah-be/overte/pull/985) adds coverage of all eight
closed AABox boundary vertices. Its
[negative qualification run](https://github.com/noah-be/overte/actions/runs/36284865697)
used a temporary inverted containment assertion. Routing selected `core` for the
single changed test file; the real graph selected only `shared-AABoxTests` and
`shared-AABoxTests-test`, with broad validation disabled.

The Qt assertion failed at the intended line. CTest reported one failed program,
zero skips, and no stale native PASS summary. The native job and required
`repository-checks` aggregate failed while host, documentation, and the other
required checks passed. GitHub reported the PR as `BLOCKED`; the active strict
ruleset still required that aggregate and had no bypass actors. The intentionally
failing head was not merged.

The [repaired native job](https://github.com/noah-be/overte/actions/runs/36285378294)
passed the same single selected program and all five AABox functions without
skips. Its cold core build took 112.586 seconds and test execution 0.066 seconds.
The broader product graph was not built for this test-only change.

## Prepared dependencies and maintenance

The corrected baseline qualified source
`ce02a328adde278323272b3866162b5c6eb348d9` and published:

```text
ghcr.io/noah-be/overte/native-dependencies@sha256:a692b477cd2efdfc1f3d0f059a8eebba4852d37509a2efa945937ef2fe073373
```

The consumer validates the recipe, Linux profile, and lockfile hashes against
image metadata before offline Conan resolution. All 43 actual package paths
match the baseline layout. Ordinary PRs use `--build=never --no-remote`; they do
not build missing third-party packages or repeat Apt setup. Dependency changes
need a reviewed replacement baseline and image. See the
[native lane guide](../tools/native-tests/README.md) for commands and diagnostics.

Compiler caches remain a speed aid, bounded to 2 GiB per saved cache. Refresh the
trusted default-branch baseline deliberately when dependencies or hit rates need
it; there is no duplicate native build on each push. Missing compiler caches can
require a cold product build: the full job limit is 90 minutes, core is 15 minutes,
dependency resolution is limited to 10 minutes, and each CTest program to 120 seconds.
The test diagnostics artifact is retained for seven days; preserve evidence
needed for longer investigations separately.

## Rollout boundaries and remaining efficiency work

Enforcement is staged on `main`; existing platform callers remain compatible.
Propagation still needs branch-specific qualification. This change does not
establish device E2E coverage or begin test-system milestone 4.

PR metadata edits can currently rerun an unchanged candidate because base-branch
changes also use the `edited` event. Developer `ci/**` and `test/**` branches
retain host push checks and can duplicate host coverage when a PR is open.
These are separate follow-up efficiency opportunities: preserve validation on
base changes and before a PR exists. Neither adds a second native push build.
