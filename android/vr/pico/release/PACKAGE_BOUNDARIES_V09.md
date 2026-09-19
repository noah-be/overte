# PI-002 offline APK boundary delta

The existing ci/verify-pico-apk.py entry is part of Pico's candidate/release
workflow and is a revision-09 authorized actual entry file. It now rejects
duplicate manifest keys, symlink/unsafe ZIP entries and oversized metadata before
decompression, bounds external verifier calls, and never echoes tool commands,
tool stderr, rejected paths, arbitrary ABI/package names or parser arguments.
Verifier-owned fixed failure categories remain useful without copying payloads.

Focused tests use only synthetic archives and mock aapt/apksigner. They cover
existing package/SDK/ABI/signature/debug-layer rules plus new privacy canaries
and duplicate/symlink negatives. No real APK has been signed, accepted or built.
The versioned Shared source graph and candidate identity/evidence/SBOM bindings
are still requested; these changes do not establish producer identity or turn
a user-supplied --source-revision into build provenance. ELF SONAME/dependency
closure and OpenSSL-3 package mapping await that actual graph contract.
