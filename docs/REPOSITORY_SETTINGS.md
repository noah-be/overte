<!--
Copyright 2026 Noah
SPDX-License-Identifier: Apache-2.0
-->

# Repository settings recommendations

This document records the intended public presentation and feature purpose for
the experimental fork. It is a handoff for a repository administrator; changing
this file does not change GitHub settings or verify their live state. The
[issue workflow](ISSUE_WORKFLOW.md) defines current task handling; the dated
observations below describe an earlier administration review.

## Description and homepage

Recommended GitHub description:

> Unofficial AI-assisted experimental Overte fork for Pico 4, Android phones,
> iPhone, and iPad; not an official Overte release.

Recommended homepage:

> https://github.com/noah-be/overte#readme

A dedicated fork website can replace the README URL later if it carries the
same experimental-fork warning and ownership boundary.

## GitHub features

| Feature | Intended policy and purpose |
| --- | --- |
| Issues | Enabled as the authoritative task source under the [issue workflow](ISSUE_WORKFLOW.md). The maintainer owns triage without a public response-time commitment. Sensitive reports use the security route. |
| Projects | Preserve existing content until an authorized inventory establishes what can be retired. Projects must not independently override Issues; [ROADMAP.md](ROADMAP.md) owns portfolio order. |
| Wiki | Disabled; versioned documentation under `docs/` is authoritative. |
| Private vulnerability reporting | Enabled; [SECURITY.md](../SECURITY.md) owns the reporting route. |
| Actions | Enabled with exact-SHA pinning and the governed action inventory; keep it synchronized with permanent branch trees. |
| Dependabot alerts | Enabled; triage findings without suppressing unresolved alerts. |
| Dependabot security updates | Enable only after generated bot PRs cannot start prohibited native product builds. A setting change needs its own verified rollout. |
| Advanced CodeQL | Use the governed GitHub-hosted workflow; do not enable default setup concurrently. |

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

## Historical observations: 2026-09-03

The Session 53X review recorded the inherited description and `overte.org`
homepage, Issues disabled, Projects enabled, and an uninitialized Wiki. Its
presentation plan kept Issues disabled, disabled Discussions and Wiki, and
retained Projects pending a content inventory. The later structured issue
workflow supersedes that historical Issues recommendation.

That review also recorded private vulnerability reporting and Dependabot
alerts enabled, security updates disabled after a safety rollback, and advanced
CodeQL active for JavaScript/TypeScript and Python. These are dated observations,
not current live checks or pending instructions. Inspect the actual settings
before an authorized administration change and retain the resulting evidence.
