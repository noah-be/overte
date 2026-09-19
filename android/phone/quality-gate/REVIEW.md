# Initial static review

Scope: the new Android Phone quality-gate directory, its callers, the existing
Phone build graph and shared device contracts. No product code was changed.
This review does not establish operational acceptance.

## Corrections made before the first local commit

- Register Android DSL changes through `beforeProject`, `withPlugin` and
  `androidComponents.finalizeDsl`, before AGP finalizes the variant model.
  Retain identical release coordinates and stable/release flags for build,
  Lint and JVM analysis.
- Include local source-built Qt JARs in the Gradle runtime inventory. Retain
  explicit unresolved-origin/license review instead of inventing Maven IDs.
- Reject empty/inconsistent Gitleaks results and incomplete ScanCode file
  inventories. Missing source entries and symlinks cannot silently disappear
  from the scan closure.
- Require a clean committed checkout at both ends of each invocation. Source
  text analysis reads the materialized snapshot; exact source exceptions use
  snapshot hashes and cannot accidentally apply to similarly named APK members.
- Bind reused build evidence with schema-2 receipts: source commit, release
  coordinates, builder identity, APK, source archive, Conan and Gradle graphs,
  release AABs, merger reports and native compile databases. Reject changed,
  missing, duplicated or symlinked evidence before reading it for later checks.
- Freeze the Gradle store inventory independently in private configuration;
  reject user init scripts/properties and symlinks in that acquisition store.
- Share bounded archive validation between extraction and device-candidate
  payload comparison. Reject encrypted/duplicate/unsafe entries and hash ZIP
  contents incrementally instead of loading every candidate member into RAM.
- Require a valid candidate APK signature and the repository's bound Phone
  adapter entry point before device work. Verify Android/physical execution,
  suite identity and digest-bound result files after each suite.
- Count actual recorded soak duration and inspect timestamp/sample coverage;
  a configured duration alone is not a successful long-running test.
- Restore report categories after nested analysis failures, preserve a failing
  final result if source/artifact bytes change, and handle SIGTERM as an
  interrupted run. Tool pins match whole version-output lines; vulnerability
  database freshness cannot exceed the reviewed 120-hour maximum.

## Static validation performed

Python files were parsed with `ast.parse`; JSON documents were parsed as data.
Shell syntax was checked with `bash -n`. Import/file references, configured suite
names and call signatures were reviewed against the existing repository files.
The staged diff received a whitespace check. None of the new Python modules
were imported or executed during this review. Gradle, scanner, build, unit,
instrumentation, E2E and long-running test commands were not run.

## Required next-step qualification

1. Provision exact scanner versions, databases, locked source/Gradle stores,
   the protected builder image and private configuration. The existing Gradle
   acquisition project includes release runtime and Lint, but not the full JVM
   test dependency closure; prepare that closure separately before offline tests.
2. Exercise failure paths with synthetic evidence once execution is authorized:
   missing/error/timeout tools, empty/inconsistent reports, changed receipts,
   duplicate/oversize archives, source mutation, invalid candidate signatures,
   unsupported/skip adapters, incomplete telemetry and partial invocation.
3. Qualify AGP DSL/task behavior and actual report paths in a real cold build.
   Static API review does not substitute for this runtime check.
4. Establish release-capable device observations. The current release APK omits
   the debug E2E launcher/probe; unsupported existing suites remain blockers.
5. Complete the source/artifact-bound manual reviews for licenses, visual
   privacy, installation/upgrade, physical behavior and profiling evidence.

No PASS release-readiness report, F-Droid submission, device acceptance, runtime
performance result or reproducibility claim is produced by this review.
