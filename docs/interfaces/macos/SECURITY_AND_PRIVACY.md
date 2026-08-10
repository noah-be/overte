# macOS security and privacy

The current milestone is a developer-local application, not a distributed
release. It has not completed a dedicated macOS privacy or security review.

- Do not place credentials, signing identities, keychain passwords, or account
  tokens in the repository, Conan profiles, CI variables, or uploaded logs.
- Treat online locations, account identifiers, microphone data, and console
  output as potentially private.
- Review microphone, local-network, camera, and input permissions before calling
  the application device-ready.
- CI diagnostic artifacts must remain bounded and short-lived and must not
  contain a developer home path or authentication material.
- Signing, hardened runtime entitlements, notarization, and Gatekeeper behavior
  remain open gates for any artifact distributed beyond its developer.

The experimental fork warning in the platform README applies independently of
the repository-level warning and must remain visible when this documentation is
copied between platform branches.
