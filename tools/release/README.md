# Android release bundle contract

`build-release-bundle.py` and `validate-release-bundle.py` define the common,
offline-verifiable contract for future Android Phone and Pico release bundles.
They do not build, sign, upload, attest, tag, or publish anything.

The builder requires all of these inputs as regular non-symlink files:

- the already verified payload and its digest-bearing verification manifest;
- the version/build coordinates bound to the same 40-character source commit;
- a source archive without links or special files;
- a ZIP containing `NOTICE.txt` and every license/notice text referenced by the
  inventory;
- a complete machine-readable license inventory; and
- a build-environment record containing the runner image, toolchain versions,
  full Action SHAs, and Conan recipe/package revisions.

The license inventory uses this minimal shape:

```json
{
  "schema": "org.overte.release-license-inventory.v1",
  "complete": true,
  "components": [
    {
      "bom_ref": "pkg:conan/openssl@3.0.0",
      "name": "openssl",
      "version": "3.0.0",
      "purl": "pkg:conan/openssl@3.0.0",
      "source": "https://openssl.org/",
      "sha256": "<64 lowercase hex>",
      "spdx_license": "Apache-2.0",
      "categories": ["conan", "native", "openssl"],
      "notice_files": ["licenses/openssl.txt"]
    }
  ]
}
```

Across the complete component set, the categories `conan`, `gradle`, `native`,
`qt`, `v8`, `openssl`, `font`, `script`, and `asset` are mandatory. Package URLs
are mandatory for Conan and Gradle components. Missing or unresolved license,
source, digest, notice text, category, package revision, or Action pin is an
error. `complete` is an explicit producer attestation and must only be emitted
after the product build has reconciled the inventory against its packaged
payload.

The deterministic output contains the payload, combined release/build
manifest, CycloneDX 1.6 SBOM, license inventory, notice ZIP, source archive,
`SHA256SUMS`, in-toto/SLSA v1 provenance, and `release-bundle.json`. Provenance
subjects cover the payload, SBOM, license inventory, notice bundle, source
archive, and checksum file. To avoid an impossible digest cycle,
`SHA256SUMS` covers every artifact except itself and provenance; the outer
bundle manifest records the provenance digest.

`.github/workflows/release-bundle-attest-draft.yml` is a reusable foundation
for both products. It downloads only a same-run bundle, validates it against
the exact tag commit, and creates separate build-provenance and SBOM
attestations with the official action pinned by full SHA. Draft creation is a
separate environment-approved job with only `contents: write`; build/signing
jobs must keep read-only repository permissions.

Do not connect that reusable workflow until the product build produces a real,
complete dependency and license inventory. A placeholder inventory must fail
closed rather than turn this contract into an unsupported completeness claim.

Both product entry points expose this contract without changing their existing
legacy candidate-metadata mode. Pass the complete set of evidence options to
`android/phone/ci/create-phone-release-metadata.py` or
`android/vr/pico/ci/pico4-release.py` to create a separate complete bundle.
Supplying only part of the set is rejected. The source archive must be the
byte-identical uncompressed `git archive --format=tar` for the recorded commit.
Legacy output is not accepted by the attestation/draft workflow as a complete
bundle because it has no `release-bundle.json` with `complete: true`.
The legacy manifests also carry `complete_release_bundle: false` and a narrow
`inventory_scope`. Legacy and complete output directories must not overlap, so
an unsuccessful complete build cannot be mistaken for upgraded legacy output.
