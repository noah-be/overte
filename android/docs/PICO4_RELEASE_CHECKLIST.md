# Pico 4 release-candidate checklist

This file is also the initial body of an automatically created **draft**. A
human release owner must complete every item before any later publication.

- [ ] Tag is `pico4-vMAJOR.MINOR.PATCH-rc.N`, protected against update/deletion,
  and targets the reviewed Pico product commit.
- [ ] Required device-free and trusted release workflow checks passed.
- [ ] APK manifest version, source revision, SHA-256 and release certificate
  fingerprint match the tag and protected environment configuration.
- [ ] `SHA256SUMS`, provenance manifest and CycloneDX SBOM were reviewed.
- [ ] Dependency checksum manifest and runner image/toolchain inventory were
  reviewed; known non-determinism was recorded.
- [ ] Default ADB-free device-acceptance inspection completed.
- [ ] Separate approved Pico 4 USB-ADB acceptance completed and its report
      matches this tag, commit, APK digest and release certificate.
- [ ] `PICO4_DISTRIBUTION_READINESS.md` portal-only requirements were rechecked
      for the selected channel and the submitted artifact digest was recorded.
  was attached. The release workflow itself never accesses a device.
- [ ] Release notes, upgrade behavior and rollback plan were reviewed.
- [ ] A release owner explicitly approved publication. Draft creation is not
  publication and this repository contains no automatic publish step.
