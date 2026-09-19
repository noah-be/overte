# iOS pre-release quality gate

Local, modular checks for the **Full Client on `apple-ios`**. No signing,
publication, release creation, Apple upload or automatic installation is part
of the default command. Android and Pico workflows are unchanged.

**Qualification status:** after the source-only implementation, a separately
authorized Linux qualification exercised regression tests and source scanners.
See [QUALIFICATION.md](QUALIFICATION.md) for evidence and remaining blockers.
The follow-up in [FOLLOWUP.md](FOLLOWUP.md) records additional triage, fixes and
the GitHub-hosted production build qualification. The task branch was published
with user authorization; no successful iOS build, signing, device acceptance or
release is claimed.
No release PASS is claimed.

Read [ANALYSIS.md](ANALYSIS.md) for the actual build graph, resource packaging,
dependency systems, existing checks and known platform limitations.

## One command

After preparing the private release configuration and evidence:

```bash
python3 ios/release-check/run.py all \
  --config /private/release-input/config.json \
  --output /private/release-results/release-001
```

Use an **absent** output directory outside the checkout for every run. It is
created as 0700; files are private. You may set `OVERTE_IOS_RELEASE_CONFIG` once
and omit `--config`. The checked-in example contains placeholders and cannot
approve a release. Configuration must be a regular, non-symlink 0600 file
outside the checkout; do not commit team IDs, device selectors or credentials.

`all` runs scanners and validates already prepared build/device evidence by
default. It **does not** silently build, install, change permissions or operate
devices. To deliberately execute new work on a prepared macOS lab host:

```bash
python3 ios/release-check/run.py all --execute-build --execute-device \
  --config /private/release-input/config.json \
  --output /private/release-results/new-campaign
```

That command can take many hours. It builds unsigned production code and runs
the existing shared suites against **separately provisioned signed E2E IPAs**.
Upgrade tests can install builds and change test-app state. Use dedicated lab
devices and the existing private Appium/native signing/fixture setup. The gate
does not acquire Apple credentials or manufacture an E2E signing identity.
Required manual assessments still need to be supplied before final approval.
For a new artifact, first collect evidence, then review it and rerun the default
command with artifact-bound reviews. A new build is not automatically approved
by reviews of an old artifact.

## Groups and status

Every group can be selected as the positional argument. `static-only` selects
the first eight groups and requires no iOS signing or device.

| Order / CLI group | Automated checks | Human boundary |
| --- | --- | --- |
| 1 `secrets` | Gitleaks current scoped files and full reachable HEAD history; credentials, keys, authenticated URLs, private IP/MAC/email/path/host candidates | Personal information, screenshots/OCR, intent, rotation and false positives |
| 2 `hygiene` | Tracked/unignored residue, keys/profiles/logs/dumps, ignore coverage, TODO/FIXME/HACK/XXX, debug/staging/mock/security-bypass/commented-code candidates | Reachability and intended developer features |
| 3 `licenses` | Source SPDX inventory, root license, media hashes, explicit asset attribution records, branding inventory | License compatibility, provenance, notices and trademark use |
| 4 `dependencies` | Conan declarations, graph verifier, SBOM generation/join, binary inventory, mutable/download-execute patterns, Grype CVEs | SDK completeness, outdated/unnecessary packages, binary/source provenance |
| 5 `static` | Python/JSON/XML/plist parsing, focused Cppcheck, ShellCheck, cmakelint, Ruff, ESLint, Swift parser if applicable | Conservative shared-code findings; QML/Metal and dynamic dispatch coverage |
| 6 `configuration` | Full Client plist, capabilities, ATS, orientation/launch keys, icon slots; source settings inventory | Unusual settings, URL handling and necessary capabilities |
| 7 `permissions` | API-to-description mapping, required-reason categories, existing privacy contract, network/telemetry candidates | Usage explanations, conditional reachability, collection, tracking and SDK declarations |
| 8 `signing` | Source entitlements, debug entitlement, distribution/capability inventory | Team ownership and distribution intent; no signing required |
| 9 `build` | Cold clone, locked Conan graph, audited SDK inputs, Release build, CMake closure, Xcode settings/analyzer, host contracts, dSYM content/UUID | Toolchain/input provenance and limits of reproducibility |
| 10 `artifact` | Safe IPA extraction/app snapshot, file inventory/hashes, strings, Gitleaks, metadata, privacy, Mach-O/runtime/arch/DWARF, test markers, signatures and profiles | Packed RCC/OCR, payload purpose, attribution and re-signing provenance |
| 11 `functional` | Existing movement/look/jump/domain/assets/sound/tablet/touch/restart/upgrade suites and exact result binding | Fresh data/installation and uninstrumented production smoke |
| 12 `robustness` | Existing domain/network-fixture/permission/lifecycle/crash/render suites | Actual link loss, screen lock, low storage, missing assets, full permissions matrix |
| 13 `long-running` | At least 4h per form factor, repeated existing suites, no skipped modules/reused result paths, time continuity, RAM/CPU/battery/thermal budgets | Instruments leaks, measurement collection, unavailable sensors, impaired networks |
| 14 `distribution` | Identity/version increase, compiled icons/launch metadata, essential permission strings, profile-specific conditions | Exact candidate acceptance; App Store-specific review only for that profile |
| Final report | Category aggregation, locations, fingerprints, criticality and recommended next steps | All warnings require release-owner attention |

- **FAIL:** blocks release and returns nonzero. Missing tools, malformed evidence,
  incomplete coverage and exceptions are failures, never skips presented as pass.
- **WARNING:** requires human review. Ordinary TODO/FIXME and conservative shared
  source candidates do not automatically block. Required named human reviews
  block until supplied; accepted reviews stay visible as WARNING.
- **PASS:** that executed category has no failures/warnings. It does not imply
  legal compliance, absence of unknown vulnerabilities or universal API coverage.

A full run prints exactly `IOS RELEASE CHECK: PASS` or `IOS RELEASE CHECK: FAIL`.
Partial group runs **always print release FAIL** because they cannot approve a
release. Their exit code is 0 when the selected checks passed; 1 means blocking
findings and 2 means setup/infrastructure failure. Do not use a partial run's
exit 0 as release approval. Consume `report.json.complete` and `result` as well.

Examples:

```bash
python3 ios/release-check/run.py static-only --output /private/checks/source-001
python3 ios/release-check/run.py permissions --output /private/checks/privacy-001
python3 ios/release-check/run.py artifact --config /private/release-input/config.json --output /private/checks/app-001
python3 ios/release-check/run.py build --execute-build --config /private/release-input/config.json --output /private/checks/cold-001
python3 ios/release-check/run.py functional --execute-device --config /private/release-input/config.json --output /private/checks/e2e-001
python3 ios/release-check/run.py long-running --execute-device --config /private/release-input/config.json --output /private/checks/soak-001
```

## Tools and prerequisites

The orchestrator requires Python 3.11+ and Git. It uses Python's standard library
and does not install anything. Install/review the required tools on the isolated
runner ahead of time; do not use `latest` containers or unpinned `npx` downloads.

| Tool | Purpose / interface |
| --- | --- |
| Gitleaks 8 with `git`/`dir` commands | Local secret/history scans, full redaction, custom privacy patterns |
| Grype | Local CycloneDX vulnerability scan; fresh public vulnerability database, High/Critical blocking even without a fix |
| Cppcheck | C/C++ defects; conservative shared diagnostics warn, iOS errors block |
| ShellCheck | Shell errors, severity `error` to avoid legacy style noise |
| cmakelint | CMake lint with whitespace/convention noise filtered |
| Ruff | Python fatal syntax/name errors only |
| ESLint 9+ | Shipped script syntax, unreachable code and `typeof`; Overte globals are intentionally not treated as undefined |
| Apple Swift parser | Conditional source parsing if Swift files enter scope |
| CMake, Conan | Existing iOS graph and cold unsigned build |
| Xcode / Clang analyzer | Actual iOS Objective-C, Objective-C++ and C/C++ analysis with SDK build settings |
| `xcrun lipo/otool/dwarfdump`, `codesign`, `security` | Architecture, load commands, dSYM and signature/profile inspection |
| Existing Python verification tools | Product metadata, privacy, static runtime, dependency graph and result identity |
| Existing Appium/XCUITest/device fixture stack | Physical functional/recovery/soak suites, only with explicit execution flag |

All non-Apple analysis tools are open source. Apple native builds/signature
inspection still require the platform's Xcode tools. There is no proprietary
scanning SaaS or source upload. Grype downloads its database, and clean builds
may download pinned dependencies; static checks are not globally offline by
default. For offline Grype, provision a current local database and set
`GRYPE_DB_AUTO_UPDATE=false`. Stale/missing databases must still fail.

`toolLocks` in private config maps tool names to `binarySha256` and
`versionOutputSha256`. A run records observed hashes and private version output,
but fails if they do not match reviewed pins. Populate locks **only after**
verifying tool source/package provenance; do not auto-copy unknown observations.
Lock the Python environment/package manager as part of host provisioning too:
hashing a Python entry script alone does not attest all installed modules.
Xcode/CMake/Conan version requirements also remain enforced by the existing build
script. Changing tool versions requires review and requalification.

## Preparing build and dependency inputs

1. Commit the intended code. Releases bind to exact Git SHA and clean worktree;
   the gate still emits inspection findings for uncommitted work but blocks it.
2. Prepare a complete reviewed Conan lockfile for `ios/conanfile.py` with the
   graphics-toolchain option and the host/device profiles. Include recipe/package
   revisions and verify downloaded source hashes. The gate never silently makes
   a new lock from floating remote state.
3. Provide SHA-256-pinned ZIP inputs for Qt iOS, matching Qt host tools, static
   non-JIT V8 and MoltenVK. `cleanBuild.inputs.*.root` points inside each archive.
   Link-containing archives are rejected; provision relocatable inputs with
   real files and audited provenance. Keep all resulting paths inside the clean
   checkout's `build-ios/external`. Host dependencies for existing Qt/Vulkan
   contract tests must be installed separately and inventoried.
4. Supply `conanGraph` and `completeSbom`. The existing Conan generator is reused
   but is not sufficient for all SDKs/assets. The complete CycloneDX inventory
   must cover Qt, V8, MoltenVK and all resolved host-context packages at exact
   versions. Include license records, provenance/hashes, and a database-recognized
   package URL or CPE for code dependencies. Inventing a purl does not establish
   vulnerability coverage. Media/software-license records remain in the license
   inventory and human completeness review.
5. Execute the `build` group later on macOS, or reference its retained
   `clean-build-receipt.json`, source checkout and File API outputs. The receipt
   must be PASS at the exact source revision. A checked-in bootstrap checkpoint
   or a successful cached incremental build cannot substitute for it.

Cold builds use a fresh local clone and Conan home. They reuse the existing
configure entry point, explicitly compile `Overte` Release, override marketing
and build versions from release intent, then inspect resolved Xcode settings and
run Xcode analysis. They neither invoke packaging that re-signs nor export to a
distribution service. A valid dSYM must remain outside the `.app`.

Conan package fetching, SDK archives and installed host tools are declared inputs,
not a hermetic OS snapshot. No bit-for-bit reproducibility claim is made.
Missing inputs or newly introduced submodules fail; extend their pinned handling
explicitly instead of reusing an arbitrary developer cache.

## Artifact identity and signing

`artifactSha256` is the IPA file hash, or for `.app` input the tree digest defined
in `artifacts.tree_digest`: sorted relative file name, executable-bit marker and
file SHA-256. Symlinks are rejected. Source artifacts are not modified; analysis
uses a private snapshot/extraction. IPA limits are 200,000 entries / 8 GiB
uncompressed; larger candidates require an explicit policy change, never a
silent partial scan. SDK input ZIPs have a separate 40 GiB limit.

The unsigned candidate's entire extracted application tree must match the cold
build. Signing changes executable bytes and introduces profile/signature files;
signed profiles therefore require an explicit `signed-build-binding` review
with `unsignedAppTreeSha256` plus the final `artifactSha256`. This is a human
provenance boundary, not cryptographic proof of binary equivalence.

Distribution modes:

- `sideload-unsigned`: unsigned developer handoff; no embedded private profile.
  A later re-signed IPA needs another artifact/signing inspection.
- `development-signed`: verify signature/profile/team/capabilities/expiry;
  debugger entitlement warns and needs developer-distribution review.
- `ad-hoc`: signed artifact and provisioning review; do not infer App Store
  suitability from this profile.
- `app-store`: signed artifact, no debug entitlement/development/ad-hoc/enterprise
  profile, plus current Apple metadata/SDK/privacy/export review. No submission.

## Device evidence and long-running tests

Configure two `deviceTargets`, one `iphone` and one `ipad`. Each has its own
private Appium configuration exposing exactly one enabled physical device.
No UDID/selector is stored in source or printed by this runner. Existing adapter
configuration/identity/security requirements still apply.

`results` maps suite names from [test-plan.json](test-plan.json) to existing
shared runner result directories. The gate invokes `verify-result.py` with
the exact expected module set, SHA, E2E IPA digest, adapter and physical class;
skips, extra/missing modules, wrong platform or stale results fail. The harness
requires the actual installed candidate to be independently verified by its
native binding. Configure controlled fixture environment and upgrade inputs
through the existing test infrastructure; this gate does not duplicate it.

Required upgrade environment includes `OVERTE_E2E_UPGRADE_FROM_VERSION`,
`OVERTE_E2E_UPGRADE_TO_VERSION`, and `OVERTE_E2E_UPGRADE_SOURCE_ARTIFACT`.
Use the existing fixture runbooks for domain/network/asset tests. See
[`tests/device/README.md`](../../tests/device/README.md),
[`IOS_TABLET_E2E.md`](../../tests/device/adapters/appium/IOS_TABLET_E2E.md) and
[`tests/device/ios/README.md`](../../tests/device/ios/README.md).

Long runs repeat the existing stability/domain/tablet/lifecycle suites for at
least four hours per form factor. `--keep-running` preserves the app between
bounded runs; process continuity must additionally be proven by resource
measurements. The existing two-hour result-format limit remains unchanged.
The application can remain running after an explicit soak; use the existing lab
cleanup procedure afterward. No automatic retry turns a product failure green.
For evidence-only mode, `longRunningResults` is a list of
`{"suite": "stability", "directory": "/private/..."}` entries. All required
suites, unique result paths, nonoverlapping timestamps and bounded gaps are
required. Routine device locks are owned by the shared runner; reserve the
dedicated lab device for the whole campaign to avoid another session between
suites.

The current iOS adapter does not provide complete cross-platform telemetry.
Collect private resource measurements using Instruments/available supported
device tooling and export this explicit normalized format:

```json
{
  "sourceRevision": "<40-character SHA>",
  "artifactSha256": "<E2E IPA SHA-256>",
  "formFactor": "ipad",
  "startedEpochMs": 0,
  "charging": false,
  "samples": [
    {"elapsedSeconds": 0, "rssMiB": 512, "cpuPercent": 80,
     "processSession": "anonymous-stable-session", "gpuPercent": 30,
     "batteryPercent": 90, "thermalState": 0, "freeDiskMiB": 10240}
  ]
}
```

The example is intentionally insufficient evidence. Use actual campaign epoch
time, >=30 samples spanning >=4h at <=120-second gaps and a stable anonymized
process-session token. CPU is percent of one logical core, thermal state is the
iOS 0..3 enumeration. Required RSS/CPU omissions, nonfinite values, mismatched
identity/timestamps or excessive budgets fail. Missing GPU/battery/temperature/
storage observation requires a specific manual limitation assessment; do not
invent telemetry. RSS growth is a warning signal for leaks, not a leak detector.
Use Instruments Allocations/Leaks for that review. Budgets in `test-plan.json`
are conservative starting values and require device-specific review.

Screen lock, actual link loss, slow/unstable links, low storage, clean-data first
launch, missing assets and permissions beyond the existing microphone test have
explicit procedures in `test-plan.json`. They are **not falsely advertised as
fully automated**. Add adapter capabilities and real assertions before replacing
these review gates with automation.

## Reviews and false positives

A required review is named by a `review-<name>` finding. Supply it privately:

```json
{
  "sourceRevision": "<exact current SHA>",
  "artifactSha256": "<production artifact SHA-256 when required>",
  "accepted": true,
  "reviewer": "<accountable reviewer>",
  "rationale": "Describe observations, retained evidence location/digest and limitations.",
  "expires": "YYYY-MM-DD"
}
```

Store it under `reviews.<name>`. E2E/production parity additionally lists every
accepted E2E hash in `e2eArtifactSha256`; re-signing additionally records
`unsignedAppTreeSha256`. Device manual case names use `iphone-`/`ipad-` plus the
case ID. The `sbom-provenance` review additionally requires `sbomSha256` for the
exact complete SBOM. Reviews are local accountable records, not authenticated attestations;
protect the input/report directories. Do not fabricate acceptance records or
mass-accept unexplained failures.

[allowlist.json](allowlist.json) contains reviewed negative-test exceptions. Copy **one exact finding
fingerprint** only after confirming a false positive, with `reason`, `owner`
and ISO `expires`. No path-wide regex exclusions are supported. Source findings
bind file content hashes, rule and location; history findings also bind scanner
fingerprints. Expired entries make the gate fail. Suppressed findings stay
visible as WARNING, and unused entries are reported. Preconditions, real tool
failures, missing evidence and vulnerability failures cannot be allowlisted.
Do not suppress an exposed credential merely because it is now revoked.

Asset provenance lives in [attributions.json](attributions.json), keyed by exact
repository-relative asset path. Each entry needs `sha256`, `source`, `license`,
`copyright`, a tracked `noticeFile`, and its `noticeSha256`. Changing either the
asset or its notice invalidates the record. Eight existing Anonymous Pro, Fira
Sans and Raleway font declarations are recorded; these are evidence records,
not compatibility opinions. Webfonts, artery fonts, compressed textures and
additional audio/video/model formats are included in the inventory.
Never infer media ownership from Overte's
root Apache license or remove legitimate contributor attribution as a privacy fix.

## Reports and privacy

`report.json` and `report.md` contain category status, rule, file/line,
description, next step, fingerprint and iOS/distribution criticality. Supplementary
JSON inventories include source scope, linked scope, permissions, licenses,
branding, dependencies, vulnerabilities, potential data egress, Xcode settings,
artifact files/manifests and device coverage. `permissions.md` gives
Permission → Component → Reason → Info.plist → Status; `licenses.md` is the
human-readable source/media attribution report. The Conan and complete SBOMs
provide machine-readable dependency license data.

Matched secret values are omitted from normalized findings. **Raw tool output,
profiles, source file names, email attribution, endpoint inventories and settings
can still be sensitive**, even with Gitleaks redaction. All outputs remain
private; never upload the directory wholesale to GitHub. Remove it under your
local retention policy after preserving reviewed minimal release evidence.

## CI integration and extension

[The manual workflow](../../.github/workflows/ios-pre-release-check.yml) runs only
by dispatch in `noah-be/overte` on a dedicated `ios-release-check` self-hosted
runner. Provision `IOS_RELEASE_CONFIG_PATH` as a repository variable containing
only the private file path, install the reviewed tools and retain outputs on
that runner. It does not trigger on pushes/PRs, touch other platform jobs, invoke
build/device execution flags or upload reports. No Jenkins job is modified.
The same local command can be called from an existing authorized laboratory job.

For new checks, add a bounded function in the appropriate module, use `ctx.add`
without matched private values, and register a group only if it is truly new.
Parse external results and fail on missing/invalid data. Add focused regression
cases to [test_gate.py](test_gate.py). Local regression invocation:

```bash
python3 -m unittest discover -s ios/release-check -p 'test_*.py'
```

The 38 Python regression tests have passed locally and cover unsafe archives, private artifact
identity, partial/full result semantics, stale reviews, expired exceptions and
scanner boundaries. Source identity also detects paths added during a run,
deletions, executable-mode changes and file/symlink substitution; independent
Android-only changes do not expand the iOS source scope. Real macOS cold build,
Appium capability coverage and resource
collection still need qualification before adoption as a trusted recurring gate.

Device evidence is checked by the existing shared verifier, then additionally
bound to the exact suite and coverage slot. Copying a result directory, changing
its JSON formatting or assigning it to another form factor cannot manufacture
another test run. Physical model/form-factor identification still requires the
private device-coverage review; the shared result schema deliberately omits UDIDs.
Synthetic telemetry tests cover stale artifacts, timestamp mismatch, sparse or
nonfinite samples, process restarts, charging, and resource-budget violations.
Passing these tests does not substitute for the real four-hour campaign.

## GitHub-hosted builds

Builds use standard GitHub-hosted `macos-26` runners, not a personal Mac, a paid
larger runner or the local Jenkins controller. On this public fork, standard
runner execution is free; artifact storage has separate GitHub accounting.
The existing `ios-bootstrap.yml` dispatch now has an opt-in `prerelease_build`
mode calling `ios-release-build.yml`, which reuses the existing Qt provisioning
and integrated Full Client build. No Android/Pico workflow is modified.

After the reviewed source branch is available in the authorized fork:

```bash
gh workflow run ios-bootstrap.yml --repo noah-be/overte \
  --ref task/ios/prerelease-quality-gate -f prerelease_build=true
```

Supply all four existing `qt_*` inputs to reuse audited Qt checkpoints, or leave
all four empty to provision through the existing Qt workflow. Production mode
sets `e2e_test_build: false`; the existing `integrated=true` mode still produces
a separate E2E build. Conflicting modes and partial checkpoint inputs fail.
Inherited workflow uploads retain unsigned IPA, dSYM and compiler checkpoint
artifacts on GitHub. This is not a release/store upload. Private scanner reports,
reviews, signing inputs and device selectors are not uploaded.

**Acceptance boundary:** the integrated workflow uses compiler/Conan caches.
Its success is useful production-build evidence, but is not accepted as the
`cleanBuildReceipt` required by this gate. The isolated cold-build driver still
needs qualification on a hosted Mac with reviewed SDK archives and lockfile.
Never substitute a cached build or an old source revision for that evidence.

## Primary references

- [Apple privacy manifests](https://developer.apple.com/documentation/bundleresources/privacy-manifest-files)
  and [required-reason APIs](https://developer.apple.com/documentation/bundleresources/describing-use-of-required-reason-api).
- [Gitleaks CLI](https://github.com/gitleaks/gitleaks).
- [Grype failure thresholds and filtering](https://oss.anchore.com/docs/guides/vulnerability/filter-results/).
- [Clang Static Analyzer](https://clang.llvm.org/docs/ClangStaticAnalyzer.html).
- [CMake File API](https://cmake.org/cmake/help/latest/manual/cmake-file-api.7.html).

Refresh Apple/platform policy review before each distribution; static API
matching cannot automate legal conclusions or establish universal privacy compliance.
