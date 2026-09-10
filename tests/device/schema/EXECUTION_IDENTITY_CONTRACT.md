# SH-004 execution-time result identity producer

Requires sh004-results/v001 + v002 and their exact Shared evidence helpers.
The existing run.py CLI remains compatible for unbound diagnostic runs. To
produce result-identity.json, supply all three additional flags:

    --candidate-artifact PATH --expected-source-sha SHA40 --expected-artifact-sha256 SHA256

The runner hashes the exact candidate bytes before discovery, rejects a wrong
hash/nonregular/symlink/empty/over-8-GiB input, and never passes claimed expected
identity to the adapter as a substitute for installation verification. Source
association is an independently frozen caller expectation, not derived from a
filename. Current hardened file access needs host O_NOFOLLOW; unsupported hosts
fail closed for bound runs. Linux/macOS are the scoped producer hosts.

Within the existing target reservation, native adapter `describe` must include:

    "executionIdentity": {
      "schemaVersion": 1,
      "sourceRevision": "40 lowercase hex digits",
      "artifactSha256": "64 lowercase hex digits",
      "installedCandidateVerified": true
    }

Exactly those nested fields/types are required. This is the actual producer
extension, not a new standalone acceptance schema. Phone/Pico/iOS own their
adapter implementation: bind to the candidate's verified provisioning/installation
receipt and recheck the installed application identity at describe time. Never
echo CLI/environment expectations, infer from app filename, invent build SHA, or
set true from a declaration alone. If the platform cannot verify it, omit the
claim or set installedCandidateVerified=false; bound execution then fails.
An IPA/ZIP's SHA identifies original installed candidate package bytes, not an
arbitrary hash of the extracted bundle. OS-specific installation attestation,
signed producer authenticity and actual build-to-source proof remain necessary.

The runner checks describe before modules and again after modules, before
cleanup releases/stops the target. It also rehashes the local candidate after
execution and immediately before emission. A missing/foreign/changed claim
adds infrastructure failure and emits no result identity. Successful binding
emits hashes of actual final run-manifest.json/summary.json/junit.xml in the
unchanged v001 result schema. Failed tests/cleanup remain failed; they may be
byte-bound but the original acceptance consumer rejects them. Legacy unbound
runs produce no identity and cannot pass the mandatory acceptance consumer.

Eight tests exercise original main(), locking, writers and original result
consumer, with only synthetic native/module boundaries: correct ordering,
missing/foreign/changed installation, changing local candidate, partial/invalid
arguments, symlink, strict boolean/type rejection, failing tests and legacy
diagnostic behavior. No devices, applications or artifacts were built/run.

This closes Shared execution-time emission, not native installation proof or
trusted producer authentication. AndroidJUnit ingestion and physical form-factor
classification are separate pending source slices. All hardware/build/dependency
acceptance and retained raw-module-log privacy remain pending.
