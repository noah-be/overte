# Pico 4 security and privacy

The APK and dependency graph are experimental and require review before use with
valuable accounts. The build and release workflows separate untrusted
device-free checks, trusted builds, signing, and physical device access.

- Keep signing keys and passwords only in the protected release environment.
- The device runner needs the expected certificate fingerprint, not the key.
- Do not expose headset serials, raw logs, microphone captures, account data, or
  complete visited locations in repository artifacts.
- Review microphone, WebView, local content, network endpoints, account/login,
  user-generated content, and store privacy declarations before distribution.
- A store may re-sign an APK; treat those bytes as a different artifact and test
  them again.

Detailed microphone and web-surface behavior is documented in
`android/docs/pico-microphone.md` and `android/docs/pico4-web-entities.md`.
