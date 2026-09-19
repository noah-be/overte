# Local qualification — 2026-09-19

After the initial source-only implementation, the user authorized proceeding
through regression tests, local tool preparation and static inspection/triage.
This is qualification evidence, not release acceptance. Reports and scanner
logs remain in a private directory outside the repository.

## Executed evidence

- All 15 gate regression tests passed: archive extraction boundaries, artifact
  tree identity, partial/full acceptance, expired exceptions, stale reviews,
  platform-specific Swift scope, scanner fingerprint stability, postponed Python
  annotations and fresh/valid vulnerability-database requirements.
- Cppcheck inspected 951 native files. Its separate deliberate double-free
  fixture was detected after repairing the local configuration-file layout.
- Gitleaks inspected the current conservative iOS scope and reachable HEAD
  history. Historical credential/key candidates remain blocking until reviewed;
  no credential values are included in normalized reports or this document.
- ShellCheck, cmakelint, Ruff and ESLint ran against the scoped files. Structured
  reports preserve individual filenames, lines, rules and exact exceptions.
- Grype detected vulnerabilities in a separate synthetic vulnerable-package SBOM.
  This verifies scanner operation only; it does not qualify Overte dependencies.
- Source configuration, permission/privacy, signing, hygiene, license and
  dependency inventories were generated through the static-only entry point.

## Local tool environment

The tools live in a separate user-local environment. Nothing was installed into
the product dependency graph or Android/Pico toolchains. Exact executable and
version-output hashes are locked in the private release configuration.

| Tool | Qualified version | Provenance retained privately |
| --- | --- | --- |
| Gitleaks | 8.30.1 | Official release checksum and GitHub asset digest |
| Grype | 0.119.0 | Official release checksum and GitHub asset digest |
| Cppcheck | 2.21.1 | Verified Fedora RPM signature/checksum |
| ShellCheck | 0.11.0 | Verified Fedora RPM signature/checksum |
| cmakelint | 1.4.3 | Wheel URL/hash in pip installation report |
| Ruff | 0.16.8 | Wheel URL/hash in pip installation report |
| ESLint | 10.11.0 | Exact npm lockfile and integrity hashes; scripts disabled |

This installation is host-specific. A macOS runner needs its own reviewed tool
installation and locks; copying Linux executable hashes cannot qualify it.

## Corrections made during qualification

- Directory-mode Gitleaks fingerprints no longer include changing temporary
  paths. Findings bind content, relative path, rule and line; history findings
  additionally retain historical identity.
- Malformed Cppcheck XML fails explicitly while allowing other linters to run.
- Linter results are structured rather than treating an entire batch as one
  failure. Existing JavaScript inline style configuration cannot override the
  gate's focused rules. Only type-only unresolved Python annotations are warnings.
- Shared CMake lexer limitations remain warnings; actual iOS configure/build
  is separately mandatory. Swift Apple-host helper parsing is deferred on Linux
  and required in the later macOS build receipt. Product Swift is never deferred.
- Credential-name matching excludes unrelated suffixed constants; the download
  execution pattern no longer matches its own pattern declaration.
- Grype database acceptance requires a valid, nonfuture database built within
  120 hours, including the nested status format of the qualified version.
- Three deliberately failing ScriptEngine fixtures have reviewed, expiring,
  exact fingerprint exceptions. No directory-wide exclusion was introduced.

## Open release blockers and manual work

- The local implementation is uncommitted; release evidence requires a clean,
  committed revision. No commit or remote publication was performed.
- Historical secret candidates and synthetic redaction/signing fixtures require
  individual disposition. Hash-looking dependency-lock entries can be false
  positives; they are not silently excluded. Do not test candidate credentials.
- Two `typeof` comparisons in `scripts/system/tablet-users.js` compare a string
  result with the value `undefined`, making the guard ineffective. The shipped
  `jsoneditor.min.js` also has diagnostics needing vendor/reachability review.
  Existing product code was not changed during gate qualification.
- A resolved production Conan graph, complete dependency SBOM, asset provenance
  and license/branding/privacy/signing reviews have not been supplied. No review
  records were invented to make the gate green.
- Conservative shared-code warnings need reachability triage against a real
  Release target closure. Static heuristics cannot establish complete privacy,
  legal, network behavior or framework provenance conclusions.
- Clean macOS build, APP/IPA inspection, physical functional/recovery tests and
  long-running resource tests remain unqualified and unexecuted. No signing,
  installation, upload, release or CI dispatch occurred.

## Repeat locally

The provisioned host has a private `ios-check` launcher that activates the locked
tools and configuration. Supply a new output directory for every invocation:

```bash
ios-check static-only --output /private/release-results/static-001
ios-check static --output /private/release-results/code-001
ios-check all --output /private/release-results/release-001
```

The portable entry point and future macOS/device execution flags are documented
in README.md. `all` does not implicitly build or operate devices. Missing required
evidence blocks acceptance; the qualified static inspection is not a full PASS.
