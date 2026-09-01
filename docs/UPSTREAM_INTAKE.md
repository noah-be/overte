<!--
Copyright 2026 Noah
SPDX-License-Identifier: Apache-2.0
-->

# Upstream intake policy

This fork permits a one-way intake of reviewed changes from the official
[`overte-org/overte`](https://github.com/overte-org/overte) repository. The
official upstream branch is `master`; this fork's default and shared branch is
`main`.

The reverse direction has a different boundary: do not submit or transplant
AI-assisted code, documentation, issues, pull requests, or review material
developed in this fork to the official Overte project. Anyone contributing
independently to upstream must follow upstream's current contribution policy
and must not use this fork as the source of AI-assisted material.

## Intake requirements

An upstream intake must:

- start from the current remote `main`, never from a platform child branch;
- fetch the exact upstream `master` revision and record its commit SHA;
- use a dedicated `sync/main/...` branch and a normal reviewed pull request;
- preserve upstream ancestry with a merge commit for a full synchronization;
- retain fork-specific contribution, security, branch, and platform policy
  unless a deliberate reviewed change replaces it;
- resolve conflicts file by file without overwriting newer fork behavior;
- run the quick project suite plus tests appropriate to every affected area;
  and
- record the fork base, upstream source, intake commit, tests, and unresolved
  differences in the pull-request description.

A selective upstream fix may be reconstructed instead of merging unrelated
upstream history, but its source commit and path selection must be recorded.
Do not present a reconstructed patch as original fork work.

## Local preparation

Use explicit remotes and branch names so `main` and `master` cannot be confused:

```bash
git remote add upstream https://github.com/overte-org/overte.git
git fetch --no-tags upstream master
git fetch origin main
git switch --create sync/main/upstream-YYYY-MM-DD origin/main
git merge --no-ff --no-commit upstream/master
```

Inspect the complete merge before committing. If the source SHA or expected
fork base changed, abort and restart the review on the new base. Never
force-push a published intake branch, rewrite published history, or merge a
platform child back into `main` as part of an intake.

## Verification and propagation

After the intake commit, run at least:

```bash
git diff --check origin/main...HEAD
python3 tests/run-project-tests.py --profile quick --timeout 240
```

Add area-specific tests based on the actual diff. Once a reviewed intake
reaches `main`, propagate it only from parent branches to their direct children
as documented in [`BRANCH_WORKFLOW.md`](BRANCH_WORKFLOW.md). An upstream intake
does not bypass branch protection, required review, or platform validation.
