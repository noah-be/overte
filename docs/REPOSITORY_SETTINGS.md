<!--
Copyright 2026 Noah
SPDX-License-Identifier: Apache-2.0
-->

# Repository settings recommendations

This document records the intended public presentation and feature purpose for
the experimental fork. It is a handoff for a repository administrator; changing
this file does not change GitHub settings. The current values below were
verified read-only on 2026-09-01.

## Description and homepage

Recommended GitHub description:

> Unofficial AI-assisted experimental Overte fork for Pico 4, Android phones,
> iPhone, and iPad; not an official Overte release.

Recommended homepage:

> https://github.com/noah-be/overte#readme

The fork currently inherits the generic upstream description and links its
homepage to `https://overte.org/`. Replacing those values with the text and URL
above makes the unofficial boundary visible before anyone clones or runs the
code. A dedicated fork website can replace the README URL later if it carries
the same warning and ownership boundary.

## GitHub features

| Feature | Current setting | Recommendation and purpose |
| --- | --- | --- |
| Issues | Disabled | Keep disabled while there is no public triage commitment. If enabled later, document response ownership and use it only for reproducible fork bugs and milestone-aligned proposals, never sensitive reports. |
| Projects | Enabled | Disable unless a maintained board is explicitly chosen to execute the roadmap. [`ROADMAP.md`](ROADMAP.md) remains the portfolio source of truth, so an undocumented parallel board adds ambiguity. |
| Wiki | Enabled, without an initialized wiki repository | Disable. Versioned documentation under `docs/` is reviewable with the code and is the authoritative documentation location. |
| Private vulnerability reporting | Disabled | Enable GitHub Private Vulnerability Reporting before soliciting private reports, then update [`../SECURITY.md`](../SECURITY.md) to link the live form. Until then, the security policy accurately states that no private technical-detail channel exists. |

Do not enable a feature merely because GitHub offers it. Before retaining or
enabling one, name its owner, intended content, relationship to versioned
documentation, and archival or triage expectation here.

## Verification after an administrator change

Record the exact setting changes outside the repository and verify them through
GitHub's repository settings or read-only API. In particular, confirm that the
public repository header shows the fork-specific description and homepage and
that every enabled feature has the purpose documented above. Enabling Private
Vulnerability Reporting also requires a separate check that an unaffiliated
reporter can see the **Report a vulnerability** action.
