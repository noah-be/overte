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

## Completed intake: 2026-09-03

The reviewed Session 52 disposition was `TAKE` for all three groups, comprising
ten content commits and four merge commits. The intake preserved their
ancestry from exact upstream tip
`b92036e6cb081666dc46af33c7fe881440e9ba50`:

- **Avatar entity privacy:**
  `406f96e4020ddc50a4206bc07f06d2466edacaab`,
  `1f8fc21eadb5b1b427c65cdfb27747189f6a3d55`, and merge carrier
  `dbd5bd811fcbd437bc820b26394015babf900df1`.
- **Create UI:**
  `313f8c66da09a1b958cf9bc39db78a339b5f8ea4`,
  `4069c4191faa6c9c63fa04fc5f8b38d4e0997acb`,
  `be648997e4829b882bca9d7405ea880d0a890488`,
  `9828a1e9124433c90abf93575a20381581a584cd`,
  `ec807f3cc453c1343d3a21e6270abd25f1eab14f`, merge carrier
  `707fdbbf4534d8289fecb2b51a5ef42054d8a155`,
  `b6b432f1586d0d4f7b056ab165d9ccc8c780e7fc`, and merge carrier
  `602b168cf559ffd489449617d8ecb65f0d1f4ece`.
- **Script errors:**
  `f5ed6e0a42e6c0e30b11b4d5389c50d7064dbc4e`,
  `d4ba0246e1446468a21adecf24c7892b609824b7`, and merge carrier/upstream tip
  `b92036e6cb081666dc46af33c7fe881440e9ba50`.

The reviewed intake head was
`77e9d0083fda4bbd620c10aca75f4870e5bc62e1`; PR #531 merged it to fork main
as `76b86a3b85ffbc9c0dad0866a668499773209c28`. The only manual selection-tool
reconciliation preserved the fork's atomic `setSelections` behavior while
accepting upstream cleanup. The ScriptEngine resolution kept both upstream's
new error path and the fork's independent heap-statistics correction. No
additional disposition is implied by this historical record.

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
