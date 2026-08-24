<!--
Copyright 2013-2019 High Fidelity, Inc.
Copyright 2020 Vircadia contributors
Copyright 2022-2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Contributing to this experimental fork

This repository is an unofficial, AI-assisted personal fork of Overte. It is
maintained as a hobby project and does not promise production support, review
capacity, release schedules, or acceptance of external contributions.

Before investing substantial work, open an issue in this fork describing the
intended outcome and target branch. The maintainer may decline or defer work
that does not advance the current milestone in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## AI-assisted work

AI-assisted issues, code, documentation, tests, and reviews are permitted in
this fork when they follow these requirements:

- disclose material AI assistance in the issue or pull-request description;
- review the complete result instead of treating generated output as evidence;
- run tests appropriate to the affected risk and record their exact commands;
- never include prompts, logs, fixtures, or artifacts containing credentials or
  private device and account data; and
- preserve copyright, license, and attribution requirements.

The official Overte project has a different contribution policy. Do not submit
AI-assisted work from this fork, including code, issues, or pull requests, to
the upstream Overte repository. Do not merge, rebase, cherry-pick, or otherwise
import new upstream changes into this fork.

## Branch ownership

Permanent branches form the ownership hierarchy documented in
[`docs/BRANCH_GOVERNANCE.md`](docs/BRANCH_GOVERNANCE.md). Target the highest
branch that owns the complete change and use a branch name accepted by
`.github/branch-policy.json`.

Examples:

```text
docs/main/project-compass
fix/android-pico/controller-input
test/android-phone/lifecycle
fix/ios/tablet-focus
```

Shared changes flow only from a parent branch to its children. Do not merge a
product branch into its parent or sibling.

## Pull requests

Keep a pull request focused on one reviewable outcome. Complete the repository
pull-request template, including:

- target layer and ownership reason;
- roadmap milestone and exit criterion advanced;
- tested platforms and exact tests run; and
- child branches that need internal propagation after the merge.

Use a merge commit for permanent-branch integration so ancestry remains
auditable. Never bypass required checks for routine work.

## Verification

For dependency-light repository checks, run:

```bash
python3 tests/run-project-tests.py --profile quick --timeout 240
git diff --check
```

Platform changes must also run the relevant branch-specific host, simulator,
emulator, or device checks. A successful host test must not be presented as
physical-device evidence.

## Bugs and feature requests

Search this fork's existing issues before opening a report. Include a minimal
reproduction, source revision, environment, observed result, and expected
result. Remove credentials, private selectors, account data, and sensitive logs.

Feature requests should explain which current or proposed roadmap milestone
they support. Store publication, broad hardware coverage, and optional parity
work may be deferred until the corresponding personal alpha is repeatable.
