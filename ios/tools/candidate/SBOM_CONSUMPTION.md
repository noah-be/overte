# iOS offline SBOM consumption

The existing handoff, simulator staging and canonical Appium preflight now require
`--sbom-contract-root PATH` for General `sh009-sbom-pair/v001`, manifest
`781c58dff5aba47b76ab52e50ceb5530956bd8b8d41876b7d6fe017b4d01753e`.
All earlier SH-002/v002, SH-009/v001, independent input, artifact, source and
whole-candidate checks remain mandatory. Use a separate Python validation
environment matching the release's requirements; no dependencies enter candidate
build inputs. There is no installation, network-schema fallback or skip flag.

The original General CLI receives independently expected source/artifact hashes
and private bounded snapshots matching the identity record's SBOM byte hashes.
Only its closed summary is returned; parser stdout/stderr is privately discarded.
Official SPDX2.3/CycloneDX1.6 validation and package/license/PURL/dependency
agreement do not prove complete iOS dependency or Mach-O contents. The original
General profile and all its limitations remain in force. No schema is copied.

Run the focused synthetic consumer check with the validation interpreter:

```text
python -B ios/tests/candidate-handoff-test.py \
  --shared-contract-root <contracts>/sh002-ios-evidence/v002 \
  --identity-contract-root <contracts>/sh009-identity/v001 \
  --sbom-contract-root <contracts>/sh009-sbom-pair/v001
```

This checks original validators plus actual candidate/preflight/staging callers;
the fixture archive is not native code and no simulator/device is launched.

The published `sh009-conan-inventory/v001` and `sh009-conan-source-join/v001`
require independently approved completed phase/checkpoint/readiness/source-ledger
inputs. The current iOS handoff supplies package evidence hashes, not those new
inputs; no matching iOS completed-phase bundle is supplied for this batch. These
two evidence joins are recorded as pending, not silently inferred from package
hashes or another platform's Cold Build. Their immutable manifests were verified:
`c259a7cc6edf59b3f337609e27745e637b8278ccbe20a1599a54b73127c43607` and
`2790968f5df77d71a6f849cd65bb30247ba618305f03974701d63b6a39080412`.
No frozen/unfinished build output is read as accepted evidence. The original
build, source/license/payload, native/signing and five legacy world/render
evidence gaps remain open.
