<!--
Copyright 2026 Noah
SPDX-License-Identifier: Apache-2.0
-->

# Repository settings recommendations

This document records the intended public presentation and feature purpose for
the experimental fork. It is a handoff for a repository administrator; changing
this file does not change GitHub settings. The values and targets below were
verified on 2026-09-03. The presentation patch follows this document's
reviewed merge.

## Description and homepage

Recommended GitHub description:

> Unofficial AI-assisted experimental Overte fork for Pico 4, Android phones,
> iPhone, and iPad; not an official Overte release.

Recommended homepage:

> https://github.com/noah-be/overte#readme

At the facts freeze the fork still inherited the generic upstream description
and linked its homepage to `https://overte.org/`. Session 53X changes both to
the exact values above after this documentation reaches `main`. A dedicated
fork website can replace the README URL later if it carries the same warning
and ownership boundary.

## GitHub features

| Feature | Current setting | Recommendation and purpose |
| --- | --- | --- |
| Issues | Disabled | Keep disabled while there is no public triage commitment. If enabled later, document response ownership and use it only for reproducible fork bugs and milestone-aligned proposals, never sensitive reports. |
| Projects | Enabled | Keep enabled until an owner or API with project-read access proves that no project content or consumer needs preservation. [`ROADMAP.md`](ROADMAP.md) remains the portfolio source of truth. The current credential cannot make that proof. |
| Wiki | Enabled at facts freeze; remote wiki repository confirmed uninitialized | Disable after this documentation merge. Versioned documentation under `docs/` is authoritative. |
| Private vulnerability reporting | Enabled | Keep enabled. [`../SECURITY.md`](../SECURITY.md) links the live private reporting route. |
| Actions | Enabled; selected exact-SHA allowlist; SHA pinning required | Keep the exact inventory synchronized with all nine branch trees; provider-wide wildcards remain disabled. |
| Dependabot alerts | Enabled | Keep alert metadata visible and triage the recorded backlog without suppressing unresolved findings. |
| Dependabot security updates | Disabled after safety rollback | Re-enable only after generated bot PRs cannot start prohibited native product builds. |
| Advanced CodeQL | Active for JavaScript/TypeScript and Python; default setup not configured | Keep the governed GitHub-hosted workflow and do not enable default setup concurrently. |

Do not enable a feature merely because GitHub offers it. Before retaining or
enabling one, name its owner, intended content, relationship to versioned
documentation, and archival or triage expectation here.

GitHub Actions storage follows the explicit cache and artifact limits in
[`CI_STORAGE_POLICY.md`](CI_STORAGE_POLICY.md). That policy does not authorize
deleting existing objects or changing repository settings.

## Verification after an administrator change

Record the exact setting changes outside the repository and verify them through
GitHub's repository settings or read-only API. In particular, confirm that the
public repository header shows the fork-specific description and homepage and
that every enabled feature has the purpose documented above. Enabling Private
Vulnerability Reporting also requires a separate check that an unaffiliated
reporter can see the **Report a vulnerability** action.

The Session 53X presentation target is therefore exact: the description and
homepage shown above, Issues disabled, Discussions disabled, Wiki disabled,
and Projects still enabled pending the missing content proof. Parent/source,
fork default branch `main`, upstream default branch `master`, visibility, merge
methods, and all unrelated settings are outside that presentation patch.
