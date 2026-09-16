# Dependency release lifecycle

The fork keeps exactly one published dependency bundle per family: Phone and
Pico. This policy concerns build inputs, independently of product releases and
the Phone, Pico and iPad Personal Alpha milestones.

## One source of truth

[`../.github/dependency-releases.json`](../.github/dependency-releases.json)
owns the current immutable tag, tag object identity, archive names and SHA-256
digests. Build scripts and release verification obtain URLs and checksum files
from `tools/dependency-releases/check.py`. Do not add versioned download URLs or
duplicate checksum files to executable sources. Do not overwrite a published
tag or archive, or use a mutable `latest` download.

Historical documentation and test fixtures may describe older packages. Old
commits retain their original metadata, but their retired downloads will no
longer be available. Rebuilding those historical commits requires separately
retained archives or a source build. No archive tags are created by retirement.

## Checks

The `dependency-release-policy` required check validates the policy and rejects
hardcoded dependency tags in executable sources. Pull requests into child
branches must use the same policy as current `main`. Policy tooling is owned by
`main` under the existing branch governance rules.

The read-only inventory workflow runs daily, on release changes and on manual
dispatch. It checks **every live remote branch**, including topic branches,
against `main`, validates current release assets and immutable tag identities,
and rejects extra dependency releases or orphan dependency tags. A failed run
is visible in GitHub Actions; it does not silently delete anything. Required
merge checks prevent drift entering permanent branches; direct topic pushes
are detected by the inventory audit. A scheduled audit is detection, not an
atomic lock on arbitrary administrator publication.

```bash
python3 tools/dependency-releases/check.py check
python3 tools/dependency-releases/check.py audit
```

## Version replacement

1. Build and test the replacement, assign a new immutable version, and publish
   its dependency archives with checksums in `noah-be/overte` only. Temporary
   overlap with the previous version is expected during this maintenance
   operation; the strict inventory check remains red until retirement finishes.
   Do not leave the operation unfinished as a normal steady state.
2. Update the central manifest through a reviewed `main` pull request, including
   the actual tag object and archive digests. Run the host tests and download /
   isolated-cache verification below. A successful archive restore does not
   replace the platform's dependency graph, build, or device acceptance tests.
3. Merge through the existing parent-to-child hierarchy, then update every
   remaining live topic branch from its owning parent. Keep historical prose
   honest. Run `check.py audit --allow-retiring`: it still requires every live
   branch to agree and every replacement archive to exist with the correct
   digest; it only tolerates additional old dependency releases/tags.
4. Review and apply the retirement plan. The tool downloads and hashes current
   archives, restores Conan archives into temporary isolated caches, repeats
   the full live audit, and deletes only strictly older dependency versions.
   Exact temporary tag-rule exclusions are restored afterward. Then run the
   strict inventory audit, leaving one release/tag per family.

```bash
python3 tools/dependency-releases/verify.py --directory /absolute/path/to/evidence
python3 tools/dependency-releases/retire.py
python3 tools/dependency-releases/retire.py --apply --directory /absolute/path/to/evidence
python3 tools/dependency-releases/check.py audit
```

Retirement requires repository administration for the temporary exact tag
exceptions. It never disables a ruleset or bypasses branch checks. It is an
explicit maintainer operation, not a scheduled destructive job. Evidence keeps
the old tag IDs and release metadata locally, without creating new Git tags.
If a branch moves, an API request fails, or replacement verification fails,
stop and repair the reported condition before retrying. Releases and tags are
separate GitHub resources: a partial failure can leave an orphan tag; the audit
detects it and a retry can finish it.

## Enforcement activation

After merging the workflow on `main` and observing a successful
`dependency-release-policy` check, add that context (GitHub Actions app ID
15368) to the existing permanent-branch ruleset. Preserve the other checks and
all branch protections. Propagate the policy to every active branch before
retiring any old bundle. Release/tag protection remains active after cleanup.

The initial rollout also retires the exact legacy Phone checksum file that
existed only on Android branches. The trusted synchronization configuration
records that file's old blob identity. Its exception permits only deletion of
that exact blob when the current parent and resulting merge both omit the path;
it cannot authorize edits, replacement content, or unrelated deletions. Large
parent deltas use complete immutable Git trees when GitHub caps comparison file
lists; truncated tree responses still fail closed.
