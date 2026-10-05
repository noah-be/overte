# Completed iOS branch integration — 2026-10-05

This integration records the original commits of completed iOS repairs alongside
their already qualified implementation on `apple-ios`. The product, build,
workflow and test trees retain the exact reviewed base
`4238b4a20d5694257083d1fbcff8a4d6cb63895d`; this receipt is the only tree addition.
Material review and conflict-resolution assistance: OpenAI Codex.

## Original source tips

| Original branch | Original tip | Current resolution |
| --- | --- | --- |
| `fix/ios/repository-coverage` | `7f6cbfd84fd86e716ba0cb2ac341410ca860f269` | The identical crash-recovery coverage correction is already present. |
| `ci/ios/bounded-compiler-jobs-20261004` | `003f880df2bc82f32e30d54a6ac5cef95f5c1d16` | The qualified parent-owned compiler budget remains authoritative. |
| `ci/ios/bounded-shared-integration-20261004` | `bf9d0645cbc8bf8b7dd12fddd1c9c9565a8d164e` | Shared HTTP and skinning repairs and the current two-job budget are retained. |
| `reconcile/ios/shared-repairs-bounded-builds-20261004` | `8f5b619783f2b82f7bfa6fd3d3cb08df4b38cb4e` | The qualified composition from PR #1046 is retained. |
| `reconcile/ios/qualified-apple-http-safelanding` | `cfa3f7a3b2c9d764af24205cb34222f4672f067a` | The incorporated HTTP/SafeLanding repair and corrected host contract are retained. |

These are normal merges of the original complete tips. Their old iOS build
settings are resolved to the qualified parent-owned `ci-build-budget.py`
implementation: CMake, Conan and the pinned Autoninja all receive the current
bounded configuration. The default client compiler limit remains two jobs.
The rejected compositions and historical test failures remain in Git history;
this integration does not claim that their original PRs passed or merged.

## Verification and boundaries

Verify all five original tips as ancestors, exact equality of every product,
build, workflow and test path with the reviewed base, the repository quick
profile, relevant iOS host contracts and the normal protected-branch checks.

The unfinished prerelease quality gate and the uncommitted Appium import change
are separate work. No issue completion, signing, device operation, release,
keep-request change or branch-protection exception is included. This receipt
adds no physical-device acceptance claim. Remote retirement remains subject to
the independent branch-cleanup checks and verified recovery procedure.

Local candidate verification: `python3 tests/run-project-tests.py --profile quick --timeout 240` passed 34/34 groups in 137.74 seconds. Full workspace documentation, whitespace and owning-branch policy checks passed. Live required PR checks remain mandatory before protected integration.
