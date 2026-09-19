# Pico SH-009 candidate binding

Pinned v001 source d01212207d9ea50cf44b9f75aed903118fd1803c; manifest
0938dcc56f67b30c4402d2bb56719b84f15628b1e3d6b5bc617bf4b93b01a1d4.
The original Shared module/CLI/contract/tests are imported unmodified separately.

The existing APK verifier consumes that module with --identity-record and the
Shared --expected-inputs, --minimum-version and six named evidence-file flags.
Pico additionally requires product=pico4, channel=internal-candidate, matching
actual APK versionCode, distinct evidence paths and independently expected source,
version name and signer. It compares the final APK digest again with the bound
identity. Do not derive expected inputs from the output being checked.

`python3 android/vr/pico/release/verify-candidate.py <same verifier arguments>`
requires the complete identity binding, with no opt-out. The existing structural
APK-only invocation remains available but explicitly reports
NOT_PROVIDED_VERIFICATION_PENDING; it is not this candidate path.

The result remains ARTIFACT_BYTES_BOUND_VERIFICATION_PENDING. Native APK signature
verification is a separate observed tool check, not a rewritten Shared verified
receipt. This version does not prove complete SPDX/CycloneDX component inventories,
producer trust, Conan PREVs/generated-output completeness, actual mandatory SH-002
build execution, graph closure, upgrade, tag/channel authorization or release acceptance.
No real candidate is created or signed by these changes. Tests use synthetic APK
metadata, mock verifier tools and deliberately test-only inventory bytes.

Check: `python3 android/vr/pico/tests/device/test_candidate_identity.py`.

## Mandatory Android build-evidence binding

Pinned sh002-android-build-evidence/v001 source
640ed7cc8e5dad9facc9d9ab655b137e834a037e, manifest
08e22323e039245a9de52b070a12403991d4c32b74f580b4f223cdd254ca0c74.
Original common terminal_evidence.py prerequisite is the exact v002 file
2033ca66e1da0b1148d1f46a6a63ee6c2f0d20df1f9d84c5413dfe6fbff2678d.
No iOS candidate schema or native iOS caller is used by Pico.

All identity-qualified invocations additionally require `--build-evidence PATH`
and `--expected-artifact-sha256 SHA256` from the independently frozen request.
The original APK verification and SH009 validator run before the ORIGINAL Shared
Android build-evidence validator, fixed to pico4. Seven distinct mandatory tiers
and their exact named checks join the record bytes, APK, toolchain and build inputs.
No diagnostic/legacy graph exemption is used to qualify a candidate.

The returned build_evidence status is
MANDATORY_TIER_BYTES_BOUND_PRODUCER_VERIFICATION_PENDING. Receipt emitters and
authenticated producer execution, real cold/warm builds, complete inventories,
signature receipts and all native/physical acceptance remain pending. Consistent
mock PASS JSON is test-only data, never evidence that its named checks executed.

The canonical Pico native binding uses this same verifier and freezes all seven
receipt byte digests along with the envelope and existing candidate inputs. It
rehashes/revalidates before and after operations. Missing/changed files deny
candidate operations, but original cleanup remains available. This is bounded
file consistency, not an adversarial atomic filesystem or device attestation.

Focused checks: original Shared8, actual Pico candidate6 (every missing tier/check,
foreign identity, absent inputs), native binding7 and legacy structural APK14 PASS.
Only synthetic APK bytes/mock signing tools/in-memory ADB boundaries were used.
