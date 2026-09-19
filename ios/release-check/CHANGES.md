# Implementation inventory

The initial additions and subsequent qualification fixes are on the local
`task/ios/prerelease-quality-gate` branch, based on `apple-ios`. The follow-up
modifies four existing files, listed below. Android/Pico workflows and Jenkins
configuration are unchanged. The task branch was published to the authorized
fork after explicit user approval; no merge or release was performed.

| New file | Purpose |
| --- | --- |
| [run.py](run.py) | Single CLI, group selection, tool locks, orchestration and source/artifact consistency |
| [common.py](common.py) | Private command/report handling, timeout boundaries, PASS/FAIL/WARNING and exact exceptions |
| [scope.py](scope.py) | Conservative iOS/shared inventory and actual Release target dependency closure |
| [source_checks.py](source_checks.py) | Secrets, hygiene/cleanup, license/branding, supply chain, syntax/analyzers, configuration, permission/privacy and source signing checks |
| [linting.py](linting.py) | Structured scoped diagnostics, annotation classification and isolated linter configuration |
| [artifacts.py](artifacts.py) | Safe IPA extraction, app snapshot, binary/file/privacy/signature inspection and distribution checks |
| [build.py](build.py) | Cold unsigned Full Client build, host contracts, Xcode analyzer/settings/targets/schemes and dSYM evidence |
| [device.py](device.py) | Existing physical iOS suites, exact result verification, campaign and resource-budget evaluation |
| [config.example.json](config.example.json) | Private release-input configuration template; no real credentials or device selectors |
| [test-plan.json](test-plan.json) | Reused suites, four-hour campaign budgets and concrete manual procedures |
| [allowlist.json](allowlist.json) | Reviewed exact, expiring negative-fixture exceptions |
| [attributions.json](attributions.json) | Initially empty, hash-bound asset provenance/notice records |
| [gitleaks.toml](gitleaks.toml) | Default secret detectors plus private path/address/email/MAC history candidates |
| [grype.yaml](grype.yaml) | Vulnerability severity, database freshness and no-ignore policy |
| [eslint.config.mjs](eslint.config.mjs) | Focused shipped-script checks without runtime-global noise |
| [test_gate.py](test_gate.py) | Regression tests for archive, acceptance, scanner and platform boundaries |
| [QUALIFICATION.md](QUALIFICATION.md) | Authorized local qualification results and remaining release prerequisites |
| [FOLLOWUP.md](FOLLOWUP.md) | Subsequent autonomous triage, fixes, validation and handoff blockers |
| [test_tablet_users.cjs](test_tablet_users.cjs) | Real bundled event-handler regression with native boundaries stubbed |
| [ios-release-build.yml](../../.github/workflows/ios-release-build.yml) | Reuse existing production build on standard GitHub-hosted macOS |
| [README.md](README.md) | Commands, tools, prerequisites, statuses, evidence, exceptions, limitations and extension |
| [ANALYSIS.md](ANALYSIS.md) | Repository/build/test/CI analysis and iOS/shared scope rationale |
| [CHANGES.md](CHANGES.md) | This complete file inventory and validation record |
| [ios-pre-release-check.yml](../../.github/workflows/ios-pre-release-check.yml) | Manual-only fork-scoped private runner workflow, no artifact publication |

| Modified existing file | Reason |
| --- | --- |
| [ios-bootstrap.yml](../../.github/workflows/ios-bootstrap.yml) | Add explicit production qualification dispatch mode; preserve other modes |
| [tablet-users.js](../../scripts/system/tablet-users.js) | Correct two ineffective typeof guards so absent fields do not trigger navigation or overwrite visibility |
| [port-contract-test.py](../tests/port-contract-test.py) | Extend exhaustive dispatch-job classification and production-mode assertions for the new hosted route |
| [personal-team-e2e-kit-contract-test.py](../tests/personal-team-e2e-kit-contract-test.py) | Update the input-count assertion to GitHub.com's documented limit of 25 |

## Original source-only implementation

- Read and traced the existing build, configuration, resource, dependency and
  device-test source files; inspected the local Git worktree state.
- Parsed newly authored Python as AST, JSON/TOML as data, and workflow/tool YAML
  as data. Read the JavaScript configuration as source.
- Reviewed inter-module calls, existing tool argument definitions, source-relative
  paths, group names and shared catalog suite names without importing/executing
  the new implementation.

**Not performed:** the new pipeline, prepared regression tests, existing tests,
scanners, dependency resolution, CMake/Xcode configure/build/analyze, signing,
device operations, workflow dispatch, Git pushes, release creation or uploads.

## Subsequent authorized qualification

The user subsequently authorized the next steps: regression tests, local pinned
tool setup, and static execution/triage. These results supersede the original
execution restriction for those steps only. See [QUALIFICATION.md](QUALIFICATION.md).

## Remaining qualification work

Prepare audited SDK inputs, lockfile, full SBOM, attribution records and private
macOS lab configuration; qualify the build and device stages separately.
The implementation intentionally cannot supply
unknown licenses, security dispositions, private signing configuration or
physical acceptance evidence. Privacy reachability, legal/branding conclusions,
E2E-to-production/re-signing equivalence, some device fault cases and resource
collection remain explicit human boundaries. GPU/thermal observation depends on
available platform tooling. See README and test-plan for each boundary.
