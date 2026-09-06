# Canonical iOS bound preflight

Consumes `sh004-ios-native-binding/v001` through General's fixed source loader
and real `appium/ios-bound.json` entrypoint. The supplied canonical class is
subclassed; target privacy, physical attestation and cleanup are not reimplemented.

Pass `--candidate-manifest` plus the existing `verify_candidate_handoff.py`
input flags, and an independently frozen `--expected-artifact-sha256`. These may
precede the runner's action. The fixed original iOS verifier checks SH-002/v002
and SH-009/v001 evidence, clean source revision, candidate bytes and independent
build inputs. It runs offline with a 90-second process-group bound, private
discarded output and no simulator execution flags. Candidate preflight does not
change or sign the candidate and does not install or start an app.

Successful describe deliberately omits `executionIdentity`. All bound invoke
and session-start paths reject until a reviewed installed-code/signature
association exists. The real v003 runner rejects missing identity; archive hashes,
bundle identifiers, expected flags and the old preinstalled receipt cannot fill
that gap. No form-factor/PID/telemetry evidence is fabricated.

Cleanup remains available without candidate arguments or after candidate files
change/disappear, using the original canonical termination implementation. The
unbound `ios.json` diagnostic mode is unchanged. Source provenance for future
execution must include this module, the original candidate verifier and its
helpers, canonical Appium/loader and pinned external Shared contracts.

Focused tests use only test candidate/OS boundaries; no device is contacted.
Reviewed installed-code identity, physical iPad/iPhone evidence and original
IO-001/002/003/004/010 acceptance remain pending.
