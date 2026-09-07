# Exact missing inputs for the iOS Conan joins

The existing candidate handoff verifies SH-002 v002, SH-009 identity and the
SPDX/CycloneDX pair. The two additional immutable contracts are:

- `sh009-conan-inventory/v001`, manifest
  `c259a7cc6edf59b3f337609e27745e637b8278ccbe20a1599a54b73127c43607`.
- `sh009-conan-source-join/v001`, manifest
  `2790968f5df77d71a6f849cd65bb30247ba618305f03974701d63b6a39080412`.

The source join executes the original phase verifier itself. Its actual CLI
`tools/sbom/join-conan-sources.py` requires all of these producer-owned inputs:

| CLI argument | Required independent or observed input |
| --- | --- |
| `--phase` | One of bootstrap, host-tools, target; separate declared graphs per phase |
| `--actual-graph` | Completed phase Conan JSON, including observed PREVs and Build/no-remote package dispositions |
| `--expected-graph` | Independently frozen phase readiness graph with matching node/edge/settings/options/license/RREV/package-ID map |
| `--checkpoint` | Actual completed phase checkpoint with exactly attempt_root, name, source_commit, manifest_sha256, recipe_index_sha256, result_sha256, jobs |
| `--expected-source-sha` | Independently authorized exact source candidate |
| `--expected-graph-sha256` | SHA256 of the frozen readiness graph, not derived from the completed result as approval |
| `--expected-manifest-sha256` | Independently frozen source-closure ledger digest |
| `--expected-recipe-index-sha256` | Frozen recipe-index digest |
| `--source-closure` | Matching original source/license ledger with package-phase/RREV joins and actual source/recipe/license identities |

The current iOS producer `resolve_dependencies()` in `ios/build-ios.sh`
exports the two static recipes and runs a single `conan install` using the iOS
host profile and macOS-arm64 build profile, an Overte remote and
`--build=missing`. It writes `<build-dir>/conan/graph.json` and
`<build-dir>/conan/sbom.cdx.json`. Neither file is the independently frozen
phase readiness graph or source ledger. This path does not create the required
phase checkpoint at all, and a cache/remote package disposition cannot satisfy
the original phase verifier's Build/no-remote requirement.

Consequently this source follow-up does not adapt or relax the original Common
schema, construct fake phase checkpoints, infer approval from package evidence
hashes, read another platform's worker/cache, or assert consumption. The
separately authorized native producer/integrator must first supply and qualify
these matching inputs (including the original independent source/recipe/license
closure), then invoke the pinned original CLI. The accepted metadata statuses
still end in CONTENT_VERIFICATION_PENDING or PAYLOAD_VERIFICATION_PENDING;
neither implies Mach-O/SBOM completeness, physical source use or native parity.
