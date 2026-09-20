# Android Phone finding remediation

Work starts from `android-phone` at `18368f8b2f77`. Earlier qualification
reports describe older commits and are not acceptance evidence for this branch.
Each correction needs a regression test or an equivalent automated invariant.
Keep credentials, scanner evidence, local paths and device identities outside Git.

## Work plan

| Category | Work and regression protection | Completion evidence |
|---|---|---|
| Secrets & Privacy | Review current detector hits, bind synthetic fixtures and symbolic constants to exact hashes; keep genuine/history findings blocking. Test changed-file, rule, expiry and history isolation. | Pending |
| Repository Hygiene / Production Cleanup | Review ignore coverage, debug/security markers and large resources; avoid bulk removal of upstream comments and functional assets. Test actual ignore behavior. | Pending |
| Licenses & Branding | Inventory notice/media coverage and resource provenance; do not invent asset licenses or remove required attribution. Test inventory coverage. | Pending |
| Dependencies & Supply Chain | Review download findings and offline test closure; preserve immutable pins and integrity verification. Test negative dependency cases. | Pending |
| Static Analysis | Preserve reviewed numeric comparison semantics; execute gate contracts and relevant existing host tests. | Pending |
| Android Configuration | Review release manifest/defaults and network policy without breaking native networking. Test release configuration invariants. | Pending |
| F-Droid Compatibility | Verify wrapper provenance and source closure; distinguish a reviewed build bootstrap from shipped blobs. Test provenance drift. | Pending |
| Clean Build | Inspect prerequisites and offline acquisition closure; never claim cold-build acceptance without execution. | Pending |
| APK/AAB Analysis | Review fail-closed artifact handling and receipt coverage; test malformed and missing evidence. | Pending |
| Functional E2E Tests | Review release observer support and suite coverage; keep unsupported execution blocking. | Pending |
| Robustness Tests | Review recovery coverage and required device evidence; preserve missing-evidence failures. | Pending |
| Long-Running Tests | Review duration/telemetry checks; test incomplete observations. | Pending |
| Final Release Readiness Report | Preserve partial-run failures and distinguish fixed findings from pending decisions and unexecuted validation. | Pending |

## Decision and evidence boundary

Historical credential revocation requires the credential owner's confirmation;
do not test credentials against services or rewrite history. Asset rights and
release identity require actual provenance or the owner's decision. Real device,
upgrade, signing and long-duration evidence must not be replaced by host tests.
No publication, release, upload or history rewrite is part of this remediation.
