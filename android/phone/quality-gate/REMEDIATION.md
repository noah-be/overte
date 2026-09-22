# Android Phone finding remediation

Current historical-secret assessment: [HISTORY-REVIEW.md](HISTORY-REVIEW.md).
The original 27 unresolved hits now comprise 11 verified public identifiers and
16 historical findings whose bound fragments are absent from current tracked
source. The local gate now reports those 16 as WARNING only after exact historical
binding and current-source absence checks; current secrets remain blocking.

Work starts from `android-phone` at `18368f8b2f77`. Earlier qualification
reports describe older commits and are not acceptance evidence for this branch.
Each correction needs a regression test or an equivalent automated invariant.
Keep credentials, scanner evidence, local paths and device identities outside Git.

## Work plan

| Category | Work and regression protection | Completion evidence |
|---|---|---|
| Secrets & Privacy | Review current detector hits, bind synthetic fixtures and symbolic constants to exact hashes; keep genuine/history findings blocking. Test changed-file, rule, expiry and history isolation. | Fixed current source false positives; reviewed inherited history warns after exact validation; new or current secrets block. Commit identity, changed bytes and expiry are tested. |
| Repository Hygiene / Production Cleanup | Review ignore coverage, debug/security markers and large resources; avoid bulk removal of upstream comments and functional assets. Test actual ignore behavior. | Fixed Phone-only log/dump ignore coverage and Git-semantic inspection. Existing maintenance/debug comments and large sky textures remain review warnings. |
| Licenses & Branding | Inventory notice/media coverage and resource provenance; do not invent asset licenses or remove required attribution. Test inventory coverage. | Fixed missing texture, font and avatar inventory formats; inventory regression passes. Asset rights and full native notices require provenance review. |
| Dependencies & Supply Chain | Review download findings and offline test closure; preserve immutable pins and integrity verification. Test negative dependency cases. | Fixed the negative HTTP-test false positive; added locked JVM/Android test acquisition and exact cache coverage. Resolved vulnerability/maintenance review awaits the release build. |
| Static Analysis | Preserve reviewed numeric comparison semantics; execute gate contracts and relevant existing host tests. | Regression suite is part of existing Phone contracts. ShellCheck comparison exception remains exact and unchanged. Android Lint/native analysis require the cold build. |
| Android Configuration | Review release manifest/defaults and network policy without breaking native networking. Test release configuration invariants. | Fixed XML formatting bypasses and broad empty FileProvider paths; mutation tests cover permissions, export, backup and debugging. Explicit network policy remains a decision. |
| F-Droid Compatibility | Verify wrapper provenance and source closure; distinguish a reviewed build bootstrap from shipped blobs. Test provenance drift. | Added early wrapper integrity enforcement and documented bootstrap origin. Public build-input and anti-feature reviews remain required. |
| Clean Build | Inspect prerequisites and offline acquisition closure; never claim cold-build acceptance without execution. | Fixed missing offline JVM test inputs, enforced local Robolectric SDKs and offline preflight. Reconciled reserve metadata with existing authorized scripts; original boundary test now passes. |
| APK/AAB Analysis | Review fail-closed artifact handling and receipt coverage; test malformed and missing evidence. | Fixed weaker AAB checks: APK and AAB now share payload checks; AAB also receives secret scanning. Actual artifacts are pending. |
| Functional E2E Tests | Review release observer support and suite coverage; keep unsupported execution blocking. | Reviewed existing suite coverage; tested that no device group runs without explicit target authorization. Release-capable observation and signed candidate still required. |
| Robustness Tests | Review recovery coverage and required device evidence; preserve missing-evidence failures. | Reviewed recovery matrix; authorization and missing-evidence blockers retained. Physical fault scenarios require dedicated lab inputs. |
| Long-Running Tests | Review duration/telemetry checks; test incomplete observations. | Fixed sparse/invalid telemetry acceptance with coverage, numeric and thermal regression cases. Actual multi-hour profiling remains pending. |
| Final Release Readiness Report | Preserve partial-run failures and distinguish fixed findings from pending decisions and unexecuted validation. | Partial runs remain full-readiness FAIL. Tests verify category failures and absent manual evidence. This branch does not claim release readiness. |

## Decision and evidence boundary

Historical credential revocation requires the credential owner's confirmation;
do not test credentials against services or rewrite history. Asset rights and
release identity require actual provenance or the owner's decision. Real device,
upgrade, signing and long-duration evidence must not be replaced by host tests.
No publication, release, upload or history rewrite is part of this remediation.


## Regression evidence

- 33 offline quality-gate tests, including negative/mutation cases.
- Existing Phone contract runner: 359 host regression assertions passed; it now
  also invokes the gate tests and the source-graph/cold-build executor tests.
- Source graph: 5 tests; cold-build executor: 7 tests. The reserve metadata test
  failed before the repair and passed after it, without changing executor behavior.
- Existing C++/Java redaction canaries, JUnit privacy test and release configuration
  checks passed.
- Test dependency acquisition succeeded with the prepared OpenJDK 17 builder;
  strict-lock resolution subsequently succeeded with Podman `--network=none`.
  No Android application build or physical device execution was performed.
- Source scan at `92f34da11e`: zero unwaived current-source secret failures;
  90 historical detector candidates and four missing review records still failed.
  Counts refer to that revision, not to a future full release report. Detailed
  scanner evidence and subsequent run summaries remain outside the repository.

## Outstanding decisions and required owner evidence

1. Historical credentials: identify owners and obtain revocation/status evidence.
   Some candidates are synthetic checksums/fixtures; high-specificity key findings
   must be reviewed separately. No credential was tested against a service.
2. Asset/dependency rights: supply provenance for unresolved media and review
   attribution, redistribution compatibility and final native notices. Confirm
   intended branding; an upstream name alone is not a legal violation.
3. Network policy: decide which public/private domains and legacy cleartext asset
   endpoints are intentionally supported before changing native/Android behavior.
4. Release identity: next version code/name, last distributed version, signing
   lineage and previous signed candidate for upgrade testing.
5. Device acceptance: choose the dedicated target and controlled domain/asset
   fixtures; decide whether to qualify a release-compatible observer or a black-box
   acceptance path. The debug probe must not be shipped merely to make tests pass.

After these inputs, still execute the cold Android build, resolved dependency/CVE
and complete license reviews, APK/AAB checks, physical acceptance and long runs.
Their results cannot be inferred from host regression tests or dependency
acquisition. F-Droid policy/anti-feature review remains a release requirement.
