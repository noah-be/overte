# macOS developer artifacts

The current release goal is limited to an installable developer application.
Store submission and public distribution are not defined.

The build is expected to produce:

```text
build/interface/Overte.app
```

Before local installation or handoff, record the source revision and a SHA-256
digest, verify the bundle executable and `Info.plist`, and run the documented
runtime smokes. Do not describe an artifact as build-ready until those gates
pass on the same bytes.

Code signing for the developer's own Mac may be added when required, but the
repository must not store a certificate, private key, keychain password, or
notarization credential. A signed, notarized, or distributable artifact requires
a separate approved process that does not yet exist.
