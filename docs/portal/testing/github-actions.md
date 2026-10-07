---
last-updated: "2026-10-07"
last-reviewed: "2026-10-07"
scope: "Shared GitHub Actions design on main; platform callers retain their own requirements"
---

# GitHub Actions

GitHub Actions checks proposed repository changes. Jenkins owns the separately
configured device laboratory. A green pull request does not establish that a
physical device was tested.

## Required repository checks

The existing `repository-checks` aggregate evaluates the selected work. Routing
can choose documentation checks, bounded dependency-tool checks, or broader
host and native checks according to the actual candidate delta. See the
[project testing guide](../../../tests/PROJECT_TESTING.md) for prerequisites and
the [maintenance guide](../../REPOSITORY_MAINTENANCE.md#required-checks) for the
required-check design.

Synchronization may reuse qualified shared host evidence only for the exact
eligible source. Branch-owned tests and independent product gates retain their
requirements. A host qualification cannot replace a selected native result.

## Native builds

The [native lane guide](../../../tools/native-tests/README.md) owns routing,
dependency preparation, caches, and diagnostics. Relevant C++ or build changes
can select real production and native test targets; known documentation-only
changes skip product compilation.

The [qualification report](../../NATIVE_CI_QUALIFICATION.md) records the
September 27 activation on `main`, actual build costs, and a failing native test
that blocked a merge. Its timings and suite counts describe that revision.
They are historical measurements, not current latency guarantees.

## Inspect a run

Open [the fork's Actions page](https://github.com/noah-be/overte/actions), select
the exact pull-request candidate or integrated commit, and inspect the failed
job before its aggregate. Match artifacts and reused evidence to that run and
revision. Distinguish a successful native job from a successful overall workflow.

Use the platform guides for Android and Apple build outputs. A verified APK or
IPA is build evidence; installed-app identity and physical behavior require
their own checks.
