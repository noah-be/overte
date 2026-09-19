# Autonomous qualification follow-up — 2026-09-19

The user authorized completing remaining steps autonomously and specified that
builds must use free standard GitHub-hosted runners. The user subsequently
authorized pushing this task branch to `noah-be/overte` and running the prepared
workflow. This does not authorize a merge, release or distribution upload.

## Completed local work

- Reviewed 97 additional exact findings: synthetic redaction/authentication/PEM
  fixtures, six synthetic parser logs, Jenkins Configuration-as-Code substitution,
  Jenkins plugin versions (including historical versions), and two harmless
  redundant vendor-JavaScript branches. Exceptions expire on 2026-12-19 and
  remain visible as WARNING. Historical redaction files were byte-compared to
  reviewed current fixtures; plugin files were checked as version coordinates.
  Combined with the three earlier negative-JavaScript-fixture exceptions, there
  are 100 exact exceptions, with no path-wide exclusion.
- Corrected two real `typeof` comparisons in the bundled `tablet-users.js`.
  The regression executes the shipped handler with native calls stubbed. Missing
  fields no longer trigger navigation or erase visibility; valid fields still
  work. It passes on the fix and fails on the original implementation.
- All 15 gate tests and the existing integrated host-handoff and recovery
  contracts passed. All 32 combinations of the five manual workflow modes were
  executed against the real validation shell step; conflicts are rejected.
- Prepared a fork-only production workflow route through existing
  `ios-bootstrap.yml`, reusing Qt provisioning and `ios-integrated.yml` on
  `macos-26`. It does not sign, create a release or upload to a store. Existing
  unsigned IPA/dSYM/checkpoint uploads are retained as CI artifacts.
- Inspected local Jenkins using the official CLI. No Mac executor is connected.
  Older successful iOS device results are not accepted for this new source.
  No Jenkins job was changed or triggered.

## Still blocking full acceptance

Ten historical secret candidates remain across five source paths: the Google
Poly integration, snapshot sharing, the two picture-frame
tutorial locations, and EntityItem's embedded historical RSA private key.
These are actual embedded credential/key candidates, not demonstrated detector
false positives. They have not been tested against services, claimed revoked,
allowlisted or removed by rewriting shared history. Credential-owner evidence is
required for disposition; raw values remain private. A further exact historical
AccountManager finding was verified as a public OAuth client identifier: the code
sends it as `client_id`, not `client_secret`. This brings reviewed exceptions to
101, without treating a real exposed credential as a false positive.

Production build and cold-build evidence remain distinct. The existing integrated
workflow uses compiler/Conan caches; it cannot satisfy the isolated cold receipt.
Resolved graph/SBOM completeness, SDK provenance, media attribution, privacy and
network behavior reviews, and candidate-bound physical-device acceptance still
need their actual evidence. No human approval records are fabricated.

## GitHub qualification

The task branch was pushed to the authorized fork and the prepared production
workflow dispatched. Run [35466963156](https://github.com/noah-be/overte/actions/runs/35466963156)
failed in host contracts before any macOS build: the existing exhaustive
workflow-job classification did not yet include the new dispatch-only job.
The existing contract now includes that job and verifies its fork restriction,
production mode and standard runner choice. The guard was extended, not removed.
Local follow-up also found an outdated assertion limiting dispatch inputs to 10.
It now follows GitHub.com's documented limit of 25. The existing port, Personal
Team, Fedora producer, world-runtime and host-handoff contracts pass locally.

No merge, release, signing or device mutation has occurred. A local report or
cached production build must not be treated as release approval while the cold
build, artifact and physical acceptance prerequisites remain missing.

## Parallel work while the hosted build runs

- Added exact records for eight fonts whose family-specific OFL notices already
  exist in the repository. Both asset and notice hashes and an immutable source
  reference are recorded. Unrelated nearby fonts are not assigned those licenses.
- Expanded the inventory to include artery/web fonts, compressed textures and
  additional media/model formats; recognize family-specific `*-OFL.txt` notices.
  Missing or changed notice hashes now invalidate attribution evidence.
- Extended source consistency checks to include added tracked/untracked paths,
  deleted files, executable-mode changes and file-to-symlink substitution.
  Six tests exercise real Git index/worktree transitions. Five additional tests
  cover attribution evidence. All 26 Python gate tests pass locally.
- Exercised all six evidence-dependent groups without candidate inputs; each
  rejects incomplete evidence and invokes no build/device command. This is a
  fail-closed boundary check, not physical-device or build acceptance.

These follow-up changes are separate from the already running build revision.
The run remains bound to its original commit; later gate changes cannot be
represented as having been executed by that run.
