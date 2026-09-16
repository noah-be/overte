# SH-002 iOS evidence adapter v1

Status: CONTRACT_READY_FOR_IMPLEMENTATION. This is a local implementation contract,
not SH-002 acceptance. The production consumer is the existing
`ios/tools/candidate/evidence_binding.py::bind_shared_evidence` entry point.

Executable: `ios/ci/evidence/verify-shared-evidence.py`. Preserve repository-relative
paths when importing this release: it loads `tests/device/schema/terminal_evidence.py`.
It accepts the existing `--candidate-metadata PATH`, `--expected-source-sha SHA40`,
`--expected-artifact-sha256 SHA256` arguments. Exit 0 means BOUND; exit 1 rejects
the evidence with a bounded error code. CLI misuse exits 2. It never prints input
paths or document content. The existing iOS verifier remains responsible for the
candidate archive bytes, package structure, producer configuration and live Git head.

The candidate JSON schema stays unchanged. Its adjacent sidecar is named
`<candidate-filename>.shared-evidence.json`. It has exactly these fields:

- `contract`: `overte-sh002-ios-evidence-v1`
- `candidateSha256`: SHA256 of the exact candidate metadata bytes
- `sourceRevision`, `artifactSha256`: the expected identities passed by the caller
- `toolchainSha256`, `normalizedInputsSha256`: digests of the actual producer input inventories
- `receipts`: four `{tier, path, sha256}` records, each pointing to a distinct regular
  sibling JSON file; paths cannot traverse directories or resolve through symlinks

Required tiers are `host-contracts`, `cold-full-client-build`,
`warm-full-client-build`, `package-verification`. Each receipt contains exactly
`contract` (`overte-sh002-receipt-v1`), `tier`, `sourceRevision`, `artifactSha256`,
`status` (`PASS`), positive integer `checks`, zero integer `failures`, `errors`,
`skipped`, and `provenance`. Unknown, duplicate, missing and invalid fields fail.
Mandatory checks cannot be skipped. Every receipt binds the final candidate;
the collector must preserve and verify the association with its underlying reports.

For build receipts, provenance contains exactly `network` (`none`), `initialCache`
(`empty` for cold, `same-source` for warm), `foreignBinaryInputs` (`false`), and the
same `toolchainSha256` and `normalizedInputsSha256` as the sidecar. Other receipts
have empty provenance objects. Warm reuse is limited to outputs of the same
source/input lineage. Source acquisition must precede network-isolated production.

The collector must derive counters and provenance from completed commands and
isolation observations. Hashes detect substitution; they do not authenticate the
producer or prove that self-reported observations are true. Producer authentication,
raw command logs, actual isolated cold/warm builds, simulator evidence and final
SH-001/SH-002 acceptance remain pending. Do not convert test fixtures to acceptance
evidence. This iOS-only slice does not substitute for Android/F-Droid scanner gates.

Conformance: `python3 tests/device/schema/test_terminal_evidence.py`.
Synthetic receipts in those tests define the exact wire format; negative cases
cover stale source, wrong artifact, missing tier, errors, skips, contamination,
input mismatch, byte tampering, duplicate JSON, path traversal and symlinks.

Migration: first version; the existing iOS adapter CLI requires no change. The
iOS owner implements real receipt collection and pins this version and its digest.
