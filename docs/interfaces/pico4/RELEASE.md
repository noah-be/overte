# Pico 4 developer artifacts

The immediate goal is a verified APK that a developer can install and test. A
store publication decision is not required for this milestone.

Use `./build-pico.sh deploy` for a debug APK on an explicitly selected headset.
For a signed candidate, the protected release-candidate workflow derives version
metadata from an immutable tag, verifies the APK and certificate, and creates a
draft GitHub release with provenance, SBOM, and checksums. It does not publish
the release.

Physical installation is a separate approved workflow. See
[`android/vr/pico/docs/PICO4_RELEASE_CHECKLIST.md`](../../../android/vr/pico/docs/PICO4_RELEASE_CHECKLIST.md)
and
[`android/vr/pico/docs/PICO4_DISTRIBUTION_READINESS.md`](../../../android/vr/pico/docs/PICO4_DISTRIBUTION_READINESS.md).
