<!--
Copyright 2026 Noah
SPDX-License-Identifier: Apache-2.0
-->

# CI storage and retention policy

This policy bounds new GitHub Actions caches and artifacts. It does not
authorize deletion of an existing cache, artifact, release, tag, or asset.
Destructive cleanup requires a fresh inventory and separate approval for the
exact objects involved.

## Cache keys and budgets

New controlled cache keys use this schema:

```text
overte-v3-<kind>-<platform>-<arch>-<toolchainHash>-<inputHash>-<generation>
```

- `kind` is a stable class such as `gradle`, `conan`, `qt`, `v8`,
  `moltenvk`, or `sccache-dir`.
- Dependency keys include the relevant lockfiles, recipes, profiles, SDKs,
  toolchains, and tool versions. Their generation is `immutable`.
- Compiler caches use at most a weekly `gYYYY-Www` generation. Permanent
  branches retain only the current and previous generations; topic branches
  retain only the current generation.
- Branch names and workflow run IDs are not part of a primary key. Restore
  prefixes become less specific only within the same platform and toolchain.
- Do not enable sccache's native GitHub Actions backend. If compiler caching is
  needed, persist one bounded `SCCACHE_DIR` archive per schema key with an
  immutable, full-SHA-pinned cache action.
- A schema-incompatible change increments the leading version instead of
  silently restoring old entries.

The warning threshold is 5 GiB or 80 entries; the working maximum is 6 GiB or
100 entries. Topic branches together may use at most 1 GiB and 512 MiB per
branch. Crossing a threshold calls for a read-only inventory first. It does not
by itself authorize deletion.

## Artifact retention

Every `upload-artifact` step sets `retention-days` explicitly:

| Artifact class | Maximum retention |
| --- | ---: |
| Successful test and contract reports | 7 days |
| Redacted failure or device diagnostics | 14 days |
| Coverage | 14 days; 30 only for an intentional baseline |
| Installable debug or development build | 7 days |
| Build-tree or compiler checkpoint | 3 days |
| Release candidate with verification evidence | 14 days |

Archived branches must not create new artifacts. Release files belong in a
draft release or an approved external evidence store only after their manifest,
digest, SBOM, license material, and provenance gates pass. Published release
objects are not general-purpose CI retention targets and must never be replaced
or deleted by routine cleanup.

The repository-level Actions retention setting is an administrative safeguard,
not a substitute for explicit workflow values. Any settings change is reviewed
and recorded separately; editing this document does not change GitHub settings.
