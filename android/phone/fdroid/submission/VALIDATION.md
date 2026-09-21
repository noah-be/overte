# Local packaging qualification — 2026-09-21

Recipe revision: `30a986c7867428606dff80c8a60ac3d9cf8d0921`.
This records local evidence, not F-Droid admission or a completed server build.
No source, metadata, APK, signing key, screenshot, or release was published.

| Check | Result | Scope and limits |
| --- | --- | --- |
| F-Droid metadata | PASS | `fdroidserver 2.4.2` readmeta and formatting lint, using current official category definitions. |
| F-Droid source scan | PASS | Zero problems after the eight explicit deletions in a disposable checkout; scanner also removes Gradle wrappers. No scanignore. |
| Buildserver provisioning | PASS locally | Provisioning script actually executed in a fresh F-Droid base container; not a complete buildserver VM run. |
| Build prerequisites | PASS locally | Exact compiler/build-tool checks, SDK inputs, user/network namespace and loopback probe. |
| Public input acquisition | PASS | All 67 locked source objects, verified Gradle 8.13 distribution, locked Gradle dependencies, and composed Qt sources acquired/prepared. No native binaries reused during acquisition. |
| Native build preflight | PASS | Newly prepared sources and empty native cache checked with external networking disabled. |
| Wrapper-independent assembly | PASS | Release assembly succeeded with wrappers and scanner exclusions removed. This incremental check reused previously source-built native libraries and application compilation outputs. |
| APK metadata/content/alignment | PASS | Expected release metadata, 483 declared assets, ELF and ZIP 16-KiB checks. |
| F-Droid APK scanner | PASS | No known non-free class/signing-block matches in the newly assembled, locally test-signed APK. This is signature-based evidence, not exhaustive dependency classification. |
| Installation and launch | PASS | Same local test certificate, installation retaining app data, successful device launch/foreground smoke test. |
| Existing Phone static suite | PASS | Includes the quality-gate, historical-secret, source-graph and cold-build regressions. Three stale hash-bound suppressions were re-reviewed as checksum values and updated narrowly. |
| Submission regressions | PASS | Ten tests, including the builder-home provisioning path, corrupt/traversal Gradle archives, clean environment, immutable staging and wrapper-independent command. |
| Complete cold adapter build | PENDING | Started separately from a clean disposable checkout with empty binary caches. Only verified source archives are reused. Completion is not established by the results above. |
| Complete `fdroid build --server --test` | PENDING | Requires a configured F-Droid builder VM and qualification of the entire recipe there. |
| Public revision | PENDING | The recipe revision is local. Metadata remains disabled until a fetchable public revision and complete server qualification exist. |

The incremental unsigned APK SHA-256 is
`05351307f6bff5280154ac15d0c53791533ff40a547f1687751362dd810a92ba`.
Compared with the prior candidate, its ZIP entry names are unchanged; only
`assets/android_rcc_bundle.rcc` and `assets/cache_assets.txt` have changed bytes.
No bit-for-bit reproducibility claim is made. The device APK uses the existing
local debug certificate solely for installation; the application itself is a
release build. A production signing key has not been created.

Private build logs, scanner JSON, regression logs, hashes and device evidence are
retained outside Git. Device identifiers and private screenshots are not part of
this submission. Earlier manual movement, look, jump and sound acceptance does
not substitute for the currently pending cold-build result.

## Decisions before publication

1. **Application identity:** the tested package is `org.overte.phone`. For a
   separately distributed fork, choose a stable fork-specific ID before the
   first public release; retain this ID only if its use is deliberately agreed.
   A change entails rebuilding and reinstalling. No ID is changed automatically.
2. **Store name:** the draft says `Overte Phone` and explicitly identifies the
   `noah-be/overte` fork. Recommend keeping the fork distinction clear. The icon
   reuses the existing Phone launcher artwork; no new branding was invented.
3. **Signing:** recommend ordinary F-Droid signing for the first F-Droid release.
   Decide separately if another distribution channel must share that identity.
4. **Publication:** recommend integrating the reviewed Phone fixes, then an
   Android-specific version tag and metadata bound to its full public commit.
   Publishing, merging, tagging and submitting still require authorization.

Missing per-asset license certificates, historic credentials not adopted by the
fork, and the separate temporary-scene/EXR-skybox observations have not been
reintroduced as blanket F-Droid blockers. Technical pending checks remain
technical work; they do not require the owner to attest that a build works.
