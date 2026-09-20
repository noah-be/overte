# Android Phone F-Droid pre-release quality gate

This local, modular gate is owned by `android-phone`. It does not publish, sign,
upload, create a release, change the application, or connect to a SaaS scanner.
The initial implementation was reviewed statically. Subsequent qualification
includes offline regression contracts wired into the existing Phone contract
suite. See [REMEDIATION.md](REMEDIATION.md) for fixes and outstanding decisions.
Scanner and build/device
qualification are separate; no release readiness is implied by these tests.

## Run later

Requires Python 3.12+, Linux, Git, the reviewed tools below, source/Gradle stores,
an immutable local builder image, and a dedicated authorized physical Phone.
Prepare a **private configuration outside the checkout** from
`config.example.json`. Commit the reviewed pipeline locally before using the
gate; every invocation requires a clean committed checkout and verifies it again
at completion. The source archive contains only HEAD. No push is required.

```sh
python3 android/phone/quality-gate/run.py \
  --config /absolute/private/android-quality-gate.json \
  --output /absolute/private/results/android-release-001
```

The output directory must not exist. Every invocation creates independent
private evidence (mode 0700, umask 077). Large cold builds can require hundreds
of GB and many hours; provision storage and resource limits on the local worker.
Nothing is installed automatically. There is no automatic sudo or SDK license
acceptance, no device discovery during configuration, and no background job.

Run one area, or several, with repeatable `--only`:

```sh
python3 android/phone/quality-gate/run.py --config /absolute/private/android-quality-gate.json \
  --output /absolute/private/results/source-001 --only secrets --only hygiene
python3 android/phone/quality-gate/run.py --config /absolute/private/android-quality-gate.json \
  --output /absolute/private/results/soak-001 --only long
```

Areas: `secrets`, `hygiene`, `licenses`, `dependencies`, `static`, `android`,
`fdroid`, `build`, `artifact`, `functional`, `robustness`, `long`.
A partial invocation returns 0 when selected checks pass, 1 for selected failures,
and 2 for initialization errors. Its **full release readiness remains FAIL**,
with unexecuted categories explicitly marked. Full runs return 0 only for an
entire successful gate; all critical failures return nonzero.

## Build and scope analysis

See [SCOPE.md](SCOPE.md) for the inspected graph and existing infrastructure.
Source scanning deliberately uses a conservative Android build/resource closure;
it does not pretend regex can evaluate arbitrary CMake/Gradle conditions.
`source-scope.json` records each scanned file and hash. After building,
`compiled-android-sources.json`, `compile_commands.json`, the three actual Conan
graphs, resolved Gradle runtime artifacts and APK inventories establish actual
compilation/package evidence. Header-only inputs, templates and assets remain
in the conservative closure even when absent from the compile database.

No iOS or Pico job is scheduled or changed. Repository hygiene examines tracked
names across the repository; reachable Git history is scanned in full so deleted
or moved Android secrets are not missed. That broader privacy audit does not
compile or modify sibling products. Common Conan files with historical `pico`
names remain relevant when the Phone graph imports them.

## Configuration and prerequisites

- `version_code`, `previous_version_code`, `version_name`: independently choose
  the next release coordinates; code must be greater than the last distributed
  code. No hardcoded proof version is used.
- `builder_image`: immutable local Podman image ID (`sha256:...`) or
  `registry/name@sha256:...`, provisioned from the existing F-Droid Containerfile.
  Tags and automatic pulls are rejected. Retain the image build provenance.
- `sdk_root`: prepared SDK 36, Build-Tools 36.0.0, NDK 27.3.13750724.
- `source_store`: acquired and verified by the existing
  `android/phone/fdroid/conan/source_closure_store.py` workflow.
- `gradle_store`: prepared by existing
  `android/phone/fdroid/scripts/prepare-gradle-store.sh`; its `COMPLETE` and
  `ARTIFACT_SHA256SUMS` are verified in the isolated copy. Source acquisition
  needs network access; the binary-producing build has `--network=none`.
- `gradle_store_manifest_sha256`: independently freeze the SHA-256 of
  `ARTIFACT_SHA256SUMS` after reviewing the acquisition store. Personal Gradle
  properties, initialization scripts, symlinks and undeclared artifact files are
  rejected. Extend the release/Lint store with `prepare-test-store.py` below.
  Its separate locked project acquires JUnit, Robolectric, AndroidX and the two
  instrumented Android SDKs. The gate resolves that project offline before the
  native build and forces Robolectric to use the staged local SDKs. Missing
  inputs remain failures; the gate never enables build networking as a fallback.
- `scancode_processes`: defaults to 2; integer range 1–8. Each worker can use
  substantial memory. Keep this low on shared workers.
- `tool_versions`: map executable names to one exact reviewed version-output line.
  No unverified release versions are invented in the template. Missing/mismatched
  versions block the relevant checks. Freeze the provisioned worker/image as
  well; a version string alone is not authenticity evidence.
- `tool_environment`: only JAVA_HOME, ANDROID_SDK_ROOT, ANDROID_HOME and
  GRYPE_DB_CACHE_DIR are allowed. PATH comes from the invoking toolchain. Grype
  requires a preprovisioned fresh database; automatic updates are disabled and
  maximum age defaults to 120 hours. F-Droid may acquire public signature data;
  no application source is sent to a hosted scanner.
- `private_markers`: optional private names/account identifiers to detect as
  literal strings; values never appear in the common report. Keep this list
  outside Git. `device_environment` accepts only the explicit local Appium,
  fixture URL/identity, AAPT, shared device lock directory and ADB key-path
  variables listed in `runtime_checks.py`. Debug/probe enabling flags are not
  accepted. Private target selection stays in the bound adapter manifest.
- `artifact` and `build_receipt`: required for independent artifact/device runs,
  pointing to a previous gate APK and `build-receipt.json`. Source and artifact
  digests must agree. Schema 2 receipts also bind the release coordinates,
  configured builder, Conan/Gradle graphs, source archive, AABs, release manifest
  origin reports and native compile databases. Missing, modified or replaced
  evidence is rejected before reuse. Keep the complete attempt directory.
  A receipt is local integrity evidence from a trusted producer, not an external
  attestation. It cannot make a partial run a full PASS.
- `adapter_manifest`, `candidate_apk`, `candidate_sha256`, `device_authorized`:
  configure the existing Phone bound adapter outside the checkout. Explicitly
  authorize the dedicated target, install the independently verified signed
  candidate through the established lab procedure, and configure local Appium
  and fixtures as documented by the existing E2E harness. The gate never signs
  or silently installs on a personal device. It requires byte-identical payload
  to the clean unsigned release APK, except signature metadata. Existing bound
  adapter arguments and source/artifact identity checks remain mandatory.
- `manual_evidence`: private review record described below. It is intentionally
  not pre-approved in the example.

The existing public `build.sh fdroid build` adapter is explicitly deferred in
this revision. This gate therefore reuses the working lower-level source-build
executor, not that deferred entry point and not the prebuilt developer setup.
The gate's small container entry point adds release coordinates, AAB generation,
Gradle dependency inventory and compile database export. Its Gradle init script
applies only to this disposable build. A fresh Conan cache is populated by source
builds from the locked closure; no personal build directories or Gradle home are
mounted. The existing source-closure and toolchain checks remain responsible
for acquisition provenance. Cold-build success is evidence of buildability,
not proof of bit-for-bit reproducibility or F-Droid acceptance.

### Acquire the test inputs once per dependency change

Use the prepared OpenJDK 17 toolchain and public network access during acquisition:

```sh
python3 -B android/phone/quality-gate/prepare-test-store.py \
  --base-store /absolute/private/release-lint-gradle-store \
  --output /absolute/private/release-and-test-gradle-store
sha256sum /absolute/private/release-and-test-gradle-store/ARTIFACT_SHA256SUMS
```

The base store is verified and copied, never modified. The output must be new.
Set `gradle_store` to this new store and independently review/freeze the printed
inventory hash in `gradle_store_manifest_sha256`. The acquisition command only
resolves dependencies; it does not build the Android application or run tests.
The checked-in `gradle-tests/gradle.lockfile` pins transitive versions. Dependency
updates require deliberate lock regeneration and an offline resolution check.
The regression suite rejects drift between Phone `testImplementation` roots and
the acquisition project. A successful acquisition is not cold-build acceptance.

## Tools (all open source)

| Tool | Purpose / license |
|---|---|
| Python / Git | Orchestration, bounded archive inspection, XML, source inventory; PSF / GPL-2.0 |
| Gitleaks | Redacted source and history secret detection; MIT |
| ScanCode Toolkit | Copyright, SPDX and package license evidence; Apache-2.0 |
| Syft | Packaged dependency discovery and CycloneDX; Apache-2.0 |
| Grype | Local vulnerability matching against resolved combined SBOM; Apache-2.0 |
| ShellCheck | Shell correctness errors; GPL-3.0 |
| Cppcheck | Android compiler-model native analysis; GPL-3.0 |
| Android Lint / AGP / Gradle | Java/Kotlin/XML/Gradle release model and JVM tests; Apache-2.0 |
| apkanalyzer / apksigner / zipalign | APK manifest, signature and alignment inspection; Android open-source tools |
| fdroidserver | F-Droid binary signature/non-free component scan; AGPL-3.0 |
| Podman / Conan / CMake / Ninja / OpenJDK | Isolated existing source build; open-source toolchain |
| Existing Python E2E / local Appium / ADB | Physical lifecycle, interaction and telemetry; no remote device service |

The Android SDK/NDK contains separately licensed components; using Android Studio
is not required. Tool licensing does not establish that every included asset or
dependency is acceptable. Keep SDK and dependency provenance under review.

References used in design (reviewed 2026-09-19):
[F-Droid inclusion policy](https://f-droid.org/docs/Inclusion_Policy/),
[build metadata](https://f-droid.org/docs/Build_Metadata_Reference/),
[fdroidserver scanner](https://gitlab.com/fdroid/fdroidserver/-/blob/master/fdroidserver/scanner.py),
[ScanCode outputs](https://scancode-toolkit.readthedocs.io/en/stable/reference/scancode-cli/cli-output-format-options.html),
[Grype CLI](https://oss.anchore.com/docs/reference/grype/cli/),
[Syft output](https://oss.anchore.com/docs/guides/sbom/getting-started/),
[AGP lifecycle](https://developer.android.com/build/extend-agp),
[AGP 8.13 AndroidComponentsExtension](https://developer.android.com/reference/tools/gradle-api/8.13/com/android/build/api/variant/AndroidComponentsExtension),
[Grype database controls](https://oss.anchore.com/docs/reference/grype/configuration/).

## Checks and blocking policy

Execution follows the requested source/privacy → hygiene → licenses/branding →
dependencies → static → Android → F-Droid → clean build → artifact → functional →
robustness → long-running → final report sequence. Android Lint, resolved native
analysis and vulnerability matching necessarily complete after their build
inputs exist; results are attributed to their original categories.

| Area | Automated evidence | Release blockers / review |
|---|---|---|
| Secrets & Privacy | Gitleaks source/full reachable history; credential/key, internal endpoint, IP/MAC, path/user/email and sensitive logging heuristics; artifact strings | Secret findings, incomplete history, scanner errors fail. Personal-data heuristics warn. Values are withheld from the common report. |
| Repository Hygiene | Tracked artifacts, IDE/temp/local config, dumps/backups, size, ignore coverage; debug/log/mock/staging, TODO/FIXME/HACK and commented code | Security-bypass patterns fail subject to exact review; ordinary cleanup comments warn. |
| Licenses & Branding | ScanCode, root notices, media inventory, branding names/resources, human and JSON reports | Unknown license/attribution cannot be accepted without mandatory component/media review. Branding is informational. |
| Dependencies & Supply Chain | Declared versions/downloads, runtime Gradle graph, Conan graphs, Syft SBOM, Grype | Dynamic versions, high/critical CVEs, incomplete inventory/tool/database failures block. Maintenance and native CVE coverage require review. |
| Static Analysis | ShellCheck errors, XML/Python parse review, Android Lint and JVM tests, Cppcheck from release compile database | Tool failures and substantive findings block; no global upstream baseline is silently accepted. |
| Android Configuration | Manifest, exported components, permissions, deep links, provider paths, backup/cleartext/trust settings; final APK identity/version/SDK/debuggable | Unexpected permissions/exports, release metadata mismatch, debuggable/testOnly/cleartext/backup violations fail. Native networking needs separate review. |
| F-Droid Compatibility | Blob origins, SDK references, source-built Conan evidence, offline build, F-Droid binary scan | Packaged suspect SDKs/non-free signatures and missing source/provenance reviews block. Names containing Google alone are not a prohibition. |
| Clean Build | Committed archive, fresh workspace/cache, pinned image, no build network, explicit unsigned release version | Any failure, absent APK or unproven graph blocks. |
| APK/AAB Analysis | Safe ZIP inventory, hashes/sizes/native libraries, unwanted assets, printable privacy heuristics, manifest merger origins, certificates, existing 16 KiB/contents checks, APK scanner; AAB contents | APK is authoritative for F-Droid; AAB is supplemental, not equivalent device acceptance. RCC/nested compressed resources and visual content need review. |
| Functional | Existing smoke, domain, assets, locomotion/look/jump, sound, tablet/touch/text and restart suites with complete capability and installed identity requirements | No mocks, skips, unsupported capabilities or mismatched candidate accepted. Clean data/install/upgrade and physical audio/touch require supporting evidence. |
| Robustness | Existing network fault, permission denial, lifecycle, domain recovery and render suites | Missing capability blocks. Lock/unlock, real WLAN changes, slow/unstable network, low storage, unreachable domains/missing assets require controlled review. |
| Long-Running | At least four hours aggregate soak in <=2h reserved sessions, interleaved domain/tablet/lifecycle cycles; RAM/battery/thermal traces, growth warning | No telemetry/short duration/failure accepted. CPU/GPU/energy/leak interpretation requires profiling evidence. This is not uninterrupted 4h process uptime. |

Warnings remain visible and do not automatically block. Required manual evidence
is a separate **FAIL until reviewed**, not an implicit waiver. The final report
contains every category and finding, location, remediation and F-Droid-critical
marker. `report.json` is machine-readable; `report.md` is the human summary.
Raw scanner reports, manifests and JUnit files are retained privately. Do not
publish raw logs, screenshots, memory dumps or scanner outputs without redaction.

## False positives and manual evidence

`allowlist.json` contains reviewed, hash-bound exceptions for intentional
length-guarded integer string comparisons, source checksum maps and Jenkins
plugin version declarations. Historical findings are not suppressed.
An exception requires exact `rule`, relative
`path`, current file `sha256`, `reason`, `owner`, and ISO `expires` date. No glob
or directory-wide suppression is supported. The finding remains WARNING and
includes its reviewed exception. Source changes/expiration invalidate it. Missing
tools, incomplete scans, device failures, history secrets and runtime artifact
SDK findings cannot be waived by this mechanism. Fix scanner configuration only
after a focused review; do not blanket-baseline historical findings.

For every ID listed in `policy.json` → `manual_reviews`, add a review to a private
copy of `manual-evidence.example.json`. Use status PASS only after the work is
done, with reviewer, reason, existing evidence file and its SHA-256. The top-level
source commit must match HEAD; artifact/device reviews additionally match the
clean unsigned APK digest. Evidence should contain procedures, observations,
versions and limits, never a bare checkbox. This record is a trusted maintainer
attestation, not cryptographic proof that its statements are true.

License evidence must reconcile packaged assets and all native/Gradle/Qt/V8/
OpenSSL components to source, SPDX expressions and distributed notice text.
Compare against the existing complete release inventory contract in
`tools/release/README.md`; merely finding a LICENSE somewhere is insufficient.
Dependency maintenance/necessity, legal compatibility, arbitrary personal data,
visual screenshots, runtime TLS behavior and genuine memory leaks cannot be
fully established by static scanners. These remain explicit human decisions.

## Device coverage and limitations

Use [DEVICE-COVERAGE.md](DEVICE-COVERAGE.md) for exact suite mappings and manual
procedures. Release APKs deliberately exclude the debug E2E launcher/probe.
Consequently some existing suites may currently lack release-capable observation;
that must fail instead of testing a debug APK and claiming release acceptance.
No product probe or export is enabled by this change. A future release-compatible
adapter/fixture path must be qualified separately under existing device identity
contracts. Signing/provisioning remains external and authorized; this gate never
uploads or signs an APK as a side effect.

## Extend and qualify

Add a check to the corresponding module and a stable finding rule; do not print
matched secrets. Add prerequisites and evidence interpretation here. Keep source
scope conservative, then refine using the real build graph. Add a new suite only
when its adapter advertises and proves its capability. Pin new tools locally,
never download and execute an unverified installer from this runner.

Before first operational acceptance (not performed during implementation), use
synthetic offline fixtures to verify: tool missing/nonzero/timeout, shallow Git,
malformed XML/ZIP/symlink/oversize members, true secret and expired exception,
unreviewed permission, CVE failure, source/artifact mismatch, skip/mock device,
missing telemetry, stale manual evidence and partial invocation. Then qualify a
full cold build and real-device campaign. Never claim the implementation itself
is a successful release check.

The initial static review, its corrections and the remaining execution-dependent
checks are recorded in [REVIEW.md](REVIEW.md). Static parsing does not validate
Gradle's runtime API, scanner behavior, source-build success or device support.

## Offline contract tests

Run `python3 -B android/phone/quality-gate/test_gate.py` from the repository root.
The tests use temporary Git fixtures and synthetic reports; they never invoke
scanners, Android builds, network services or devices. They cover missing tools,
timeouts, command failures, partial readiness, source mutation, missing and
inconsistent secret reports, exact exceptions, required manual review, unsafe
evidence paths, archive limits and failure-category attribution. These are not
a substitute for real scanner, build or device qualification.

The first source qualification detected an ISO timestamp misclassified as a
dynamic dependency. Regression cases now distinguish timestamps from real
`+` and `SNAPSHOT` dependency coordinates. Scanner concurrency is explicitly
bounded after the initial ScanCode default exhausted much of the worker memory.
