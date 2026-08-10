# iOS security and privacy

The detailed source-backed privacy inventory remains in
[`docs/ios/PRIVACY.md`](../../ios/PRIVACY.md), with dependency and license
evidence in [`docs/ios/COMPLIANCE.md`](../../ios/COMPLIANCE.md).

The app keeps App Transport Security enabled and does not declare tracking
domains. Microphone and local-network prompts are usage declarations rather
than signing entitlements. New permissions, capabilities, endpoints, SDKs, or
required-reason API categories require an explicit review.

Certificates, provisioning profiles, private keys, keychain passwords, Apple
credentials, and App Store Connect keys must never enter the repository or
ordinary CI artifacts. Diagnostic uploads must be bounded and sanitized.

The integrated client's account, voice, telemetry, and crash-report behavior
still requires runtime review before privacy declarations can be treated as
final.
