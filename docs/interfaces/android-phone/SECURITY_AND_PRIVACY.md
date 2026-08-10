# Android Phone security and privacy

The Phone port remains experimental and has not completed a production security
or privacy review.

- The APK uses the independent package `org.overte.phone` and an explicit
  permission allowlist verified from the merged binary manifest.
- Microphone permission is optional for world access. Denial must remain a
  supported path.
- Cloud backup and device-to-device transfer are disabled for application data.
- Raw Logcat, screenshots, device serials, complete deep links, account data,
  performance traces, and private host paths must remain temporary and private.
- Signing keys and passwords must remain outside the repository. The current
  store-neutral candidate intentionally contains no signing secret.
- A future signed channel needs its own approved key custody, recovery, rotation,
  and publication runbook.

Device and benchmark scripts minimize reported data, but this is not a substitute
for a full source and runtime privacy review.
