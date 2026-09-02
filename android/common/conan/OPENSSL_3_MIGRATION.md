# OpenSSL 3 migration plan

OpenSSL 1.1.1q is unsupported and must not be treated as a maintained release
dependency. The selected destination is OpenSSL 3.5.8, the current security
patch on the 3.5 LTS line supported through April 2030. Release and support
status must be rechecked against the
[OpenSSL 3.5 release notes](https://www.openssl-library.org/news/openssl-3.5-notes/)
and [OpenSSL roadmap](https://www.openssl-library.org/roadmap/) when each slice
is implemented.

A single version substitution is unsafe in this tree. The Android APK staging
contract, 16 KiB verification, legacy Gradle projects, Windows deployment
helper, custom libnode recipe, and prebuilt dependency archives all name or
link the 1.1 ABI. The committed target lockfiles make that coupling visible.

Migrate in independently reviewable slices:

1. Verify Linux desktop and server builds against their existing system
   OpenSSL 3 installation, including networking, RSA, HMAC, WebRTC compatibility,
   and packaging tests. This lane does not consume the bundled 1.1 binaries.
2. Add an OpenSSL 3.5.8 Conan graph for source-built desktop Qt. Update and test
   Windows DLL deployment as a separate change; do not mix it with AQT binary
   compatibility work.
3. Teach the custom libnode recipe to consume the OpenSSL 3 provider ABI and
   test Node, Qt network/TLS, and Overte networking together before changing an
   Android profile.
4. Migrate one Android profile at a time. Update the Gradle staging names, APK
   content checks, 16 KiB ELF checks, runtime loader tests, and that profile's
   Conan lockfile in the same change.
5. Rebuild prebuilt dependency archives from the reviewed lock, publish them
   only with a new immutable tag and checksum manifest, and verify both offline
   restore and source-build parity. Never reuse or replace an existing archive.
6. Remove the final 1.1 recipe references and compatibility paths only after
   every target lock and packaging test is green.

Required evidence for each slice is the exact source commit, Conan version,
host and build profiles, lockfile digest, dependency graph, compile/link tests,
packaged-library inventory, TLS smoke tests, and—on Android—the page-alignment
verification. Until that evidence exists, the corresponding 1.1 target remains
a known blocker and must not be represented as release-ready.
