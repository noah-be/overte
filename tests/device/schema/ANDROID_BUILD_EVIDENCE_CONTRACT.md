# SH-002 Android mandatory build-evidence join

IMPLEMENTATION ONLY, not SH-002 PASS. Source-level prerequisites: sh002-ios-evidence/
v002's common tests/device/schema/terminal_evidence.py parsing helpers and
sh009-identity/v001's provenance/artifact_identity.py. The iOS candidate/envelope
schema is NOT transplanted into Phone/Pico; existing iOS behavior is unchanged.

Executable Shared consumer: android/phone/fdroid/scripts/verify-source-only.sh.
It performs only this read-only evidence join; despite the historical planned
filename it does NOT execute a build, scanner, signer, loader or device test.
Exact mandatory arguments:

```
--build-evidence PATH --identity-record PATH --artifact PATH
--expected-inputs PATH --expected-source-sha SHA40
--expected-artifact-sha256 SHA256 --product android-phone|pico4
```

Native Phone/Pico candidate verifiers retain ALL existing SH-009, version,
channel, package and signature checks. They additionally call
tests/device/schema/android_build_evidence.py::validate(evidence_path,
identity_record_path, artifact, expected_inputs_path, source_sha,
artifact_sha256, product), or invoke the executable with those exact arguments.
Missing build evidence must reject a build-qualified candidate; diagnostics may
remain distinctly unqualified. No native-owned caller is changed by General.
Phone's existing --shared-evidence-contract path/digest can pin this document;
that pin is NOT an executed tier receipt. Native owners add their actual
--build-evidence input and preserve existing independently pinned expectations.

The existing SH-009 record's raw digest, actual artifact bytes, exact expected
eight-key normalized inputs and toolchain are joined to a new Android evidence
envelope. SH009 inventory/signature/upgrade semantics are not reimplemented or
upgraded by this join: native original validators remain mandatory. Expected
inputs/source/artifact come from the independently frozen build request, never
copied from an untrusted output manifest. Cold/warm receipts must bind the same
exact candidate bytes and effective inputs, not merely similar settings.

The closed envelope/tier fields and mandatory named check sets are defined in
android_build_evidence.py and exercised by test_android_build_evidence.py. Every
product requires host-contracts, cold-full-client-build, warm-full-client-build,
source-license-closure and package-verification. Phone additionally requires
fdroid-source-scanner and elf-loader-verification (16KiB/SONAME/API26). Pico
requires source-graph-compatibility and pico-package-verification; this modern
Shared graph path cannot claim an unaffected legacy graph to skip them. Pico's
F-Droid distribution itself remains optional, not silently required here.

Each named check must record PASS, a strictly positive integer executed count,
and integer zero failures/errors/skips. A tier-level PASS or positive generic
count cannot replace the exact named checks. No N/A/skip aliases, unknown checks,
binary fallback, foreign cache, network-enabled build or different warm inputs
are accepted. Scanner errors are nonpass. Receipts use distinct bounded regular
JSON files in the envelope's directory, no traversal/symlink/hardlink aliasing.
All receipt digests and source/artifact/input joins are checked and bytes
rechecked at completion. Duplicate JSON keys and nonfinite data fail closed.
Input/parse failures print closed codes, never user paths or arbitrary values.

Success is deliberately
MANDATORY_TIER_BYTES_BOUND_PRODUCER_VERIFICATION_PENDING. Authenticating the
producer and its execution, implementing actual receipt emitters in the
controlled build/scanner/native verifier, semantic inventories/SBOMs and all
original artifact/physical gates remain required. A forged set of internally
consistent PASS JSON cannot prove execution; no trusted=true field is accepted
or inferred. This is not a source-only candidate admission or Issue closure.

Tests use explicitly non-APK fixture bytes, generated mock receipts and the
ORIGINAL SH009 validator followed by this join. Both product plans, every absent
tier/check, failures/skips/booleans, scanner error, source/artifact/toolchain/cache/
network mismatch, reused files/traversal, altered bytes and actual shell/closed
CLI errors are checked. No full suite, APK, signing, build or device run occurs.
