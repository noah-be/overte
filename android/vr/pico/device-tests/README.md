# Pico universal device adapter

Revision 09 hardens this existing production entry point: operations require a
recognized authorized Pico; unknown Guardian/seethrough properties cannot pass;
stale/future world timestamps cannot report connected; private place text is
omitted. Foreground-package observation is still only an OS proxy for focus,
not proof of XrSessionState or worn-headset/controller acceptance. The canonical
SH-004 offline result binding is described below. Negative tests run exclusively
with in-memory transport under `tests/device/test_adapter_negative_boundaries.py`.

## Revision 09 result consumer (offline)

`python3 android/vr/pico/device-tests/verify-result.py --result-dir <run-directory>
--expected-source-sha <candidate-source> --expected-artifact-sha256 <candidate-hash>
--required-module <reviewed-module>` consumes the original SH-004 v001 verifier.
Repeat required-module for the complete reviewed milestone, not only successful
modules. It performs no discovery, ADB, producer-sidecar generation or device run.
It pins the released android/pico-bound.json identity android-pico-adb and its actual
platform=android. It rejects Phone, virtual, wrong-source/artifact, incomplete,
skipped, altered and privacy-unsafe results with a closed diagnostic.

SH-004 v001 source 5c6354555a88fac2e089b033eb52ebe750171cd5, manifest
d92c7710551fe134029d2243cea84350a18000934acbd765bd1ef138b3cfa85b.
Its included original terminal_evidence.py helper is imported unchanged as a
separate source prerequisite; the iOS candidate schema is not adopted by Pico.
SH-003 v001 source 557f1612ece5bb77c6a888922255994376833f41, manifest
fbed00861eec9e422623ebcb42f93d6c0eeee5ee1df8ccb78182b80d44d8166d is
consumed through its actual FileUtils selector caller. Pico retains Pico/Quest
presentation priority and never turns required control behavior into an observed
capability. Shared QML focus/geometry/control enforcement remains pending.

Success is RESULT_BOUND_NOT_NODE_ACCEPTED, not a headset result or trusted
producer attestation. Authenticated producer evidence, full capability-gap
classification, private module/pixel/crash scans and physical controllers remain
pending. Host fixtures declare physical metadata only to exercise validation;
they are not admissible device receipts and are discarded with test scratch.

## Bound canonical execution — source implementation only

SH-004 android-native-binding/v001 and required v002 are consumed unchanged.
v002 source: 393811b10f971e86ca13d2b472eaaf736b9f6981; release manifest:
9f9d9a9f7720638770709d2d07c9240259b3cbb7faa574f7c2e6e812fe016075.
The real canonical Android CLI loads owned
tests/device/adapters/pico4/binding.py and gives it the actual AndroidAdapter
class. No duplicated Android adapter, substituted result schema, or environment
identity claim is introduced. The legacy android/pico.json is unbound diagnostics.

For a separately authorized future run, the private execution manifest keeps
the released pico-bound.json ID/schema and uses the absolute canonical adapter
path followed by its --kind pico --native-binding options and independently
pinned candidate arguments. The runner appends the action afterward. Required
native inputs are the original Pico verifier's --apk (named form of its existing
positional input), --aapt, --apksigner, --source-revision, --expected-version-code,
--expected-version-name, --expected-signer-sha256, --identity-record,
--build-evidence, --expected-artifact-sha256,
--expected-inputs, --minimum-version and all six original SH009 inventory flags.
The optional original E2E-layer constraints are retained. There is no native
--output side effect. Missing inputs fail before constructing a device adapter.
No private manifest or actual APK/device invocation is created by this handoff.

The original Pico verifier is now also callable without printing a manifest;
both CLI forms still use the same structural/signature/SH009 implementation.
The binding freezes input-file digests (including local verifier tools), checks
them before/after original validation, and revalidates on describe and around
operations. It queries the same selected target's PackageManager path for the
fixed org.overte.pico package, accepts one monolithic /data/app/.../base.apk only,
and compares two actual OS sha256sum observations with the validated candidate.
Package mapping is checked around both reads. Missing hashes, paths containing
shell syntax, splits, changed mapping, altered local evidence/candidate and
foreign installed bytes reject without an identity. No expected-hash echo is
used as an OS measurement. A rooted/compromised OS is not remotely attested.

The bound suite starts with that candidate already provisioned. app.install may
only reinstall that exact local candidate and is checked before/after; a foreign
initial installation and one-candidate app.upgrade are rejected. Cleanup retains
the canonical force-stop/confirmation path even after missing/invalid candidate
files and never emits an executionIdentity. An extra repeated check does not
make package replacement atomic with an entire operation; real device timing,
tool availability, input/metrics overhead and adversarial device behavior remain
unverified. Bound execution is deliberately not the unbound diagnostics path.

Focused tests run the actual canonical parser/loader/dispatch, original Pico
candidate verifier, original SH004 producer and Pico result consumer with only
synthetic APK/signature tools, in-memory ADB and a test module. The positive
identity and physical metadata are test substitutes, not installed-device proof.
Post-module foreign bytes prevent actual result-identity emission. Original
SH009 signature/upgrade receipts remain pending; signer trust, producer/SBOM
authenticity, full build, all physical steps and node acceptance remain deferred.

This adapter reuses the shared Android ADB transport and adds Pico identity,
XR-focus, Guardian/seethrough, and world-status operations. It intentionally
does not advertise phone-style background lifecycle support.

## Semantic tablet acceptance

The complete Tablet-E2E contract uses the product Pico profile in
`tests/device/adapters/android/pico.json`, not the legacy smoke-only manifest
in this directory. Its checked-in product policy is
`pico4-tablet-policy.json`.

Run hardware-free contract checks first:

```bash
python3 -m unittest tests.device.self_tests.test_tablet_e2e -v
python3 android/vr/pico/tests/pico-tablet-e2e-adapter-test.py
```

A physical run requires the E2E Debug APK, the qualified explicit OpenXR
layer, one Pico on the private isolated ADB server, and the private runtime
state directory documented in
`tests/device/openxr_input/PICO4_CONTROLLER_AUTOMATION.md`. With those gates
provided by the private lab environment, run:

```bash
python3 tests/device/run.py \
  --adapter-manifest tests/device/adapters/android/pico.json \
  --catalog tests/device/catalog.json --suite tablet-e2e \
  --tablet-policy android/vr/pico/device-tests/pico4-tablet-policy.json \
  --require-complete --output-dir /tmp/overte-pico-tablet-e2e
```

Do not put the private target selector, ADB server port, device serial, or
runtime directory in this command or in persisted reports. The lab wrapper
supplies them through its protected environment and device lock. A pass
requires the complete open → Home ready → visible Settings pointer activation
→ Settings ready → General/HMD and Graphics/render-resolution policy checks →
Home → close sequence in one process. The probe snapshots before and after the
tablet-focused sequence must also prove stable avatar position, velocity and
view orientation.
