# Pico protected storage

Revision 09 production slice, PI-002/PI-003; node acceptance is pending.

SecureAccountStore uses AndroidKeyStore AES-256/GCM keys and bounded authenticated
records under Context.getNoBackupFilesDir(). The envelope authenticates its
version and purpose. Each slot has its own key. Writes require authenticated
readback; reads never generate a replacement key. Removal deletes both key and
record. All operations are serialized in this process. This is not multi-process
storage and does not promise rollback protection against a compromised process.

RestartArguments is the current production caller. It deletes old plaintext
transient restart arguments instead of importing them, encrypts new arguments,
and removes the protected record before returning a consumed handoff. Storage
errors cancel the handoff. No account credential migration is performed here.

PX-15 v001 is pinned to source 3ca00141a74d75ea94195d79880f74f8a9550016,
manifest db934a5a0b2b8bc41aefde437fb85886ea577c59cb4de4e3bbbd539ed29301ed.
Its unmodified Shared migration/AccountManager patch is imported separately
(local commit b46806e2255dcf69d0aec61f9ac8437ba1834b89). PicoAccountStoreBridge
uses the literal account-map-v1, maps typed failures without exception text,
and clears transient Java arrays. PicoAccountStore.cpp implements the actual
Shared interface, attaches native worker threads, clears pending JNI exceptions
without describing them, bounds copies and clears Java plaintext after copying.
PicoInterfaceActivity prepares the application-context peer before Qt startup.
The CMake entry adds only this adapter to picoOpenXR; it does not link another
static networking coordinator into that early-loaded library.

General released the precise Application_Setup hook in parallel-v09/HOOK_RELEASES.md
(observed SHA256 1ec7c5906f0e4e08d1ee76ee0bce110fba40e05d24cf8d58b7606a8a392f96ea).
The separately committed delta includes ../security/PicoAccountStore.h and
registers its factory before the first AccountManager construction. Failed
registration emits only OVT_STORAGE_UNAVAILABLE. No other startup behavior is
changed. The hook retains the existing networking/coordinator instance and is
explicitly reserved for General's later SH-011 minimal-seam review. Full Qt
caller compilation and real account login/migration remain unverified.

Android Keystore hardware backing, locked/key-invalidated/orphaned records,
upgrade/logout/power interruption and durable ambiguous-operation recovery need
headset acceptance. File access errors are not mapped to absence. Tests prove
API-26 compilation, authenticated crypto with test-only JVM keys, and actual
production Java/JNI plus Shared migration against an injected test-only backend.
They do not execute AndroidKeyStore. PX-16 sinks are a separate binding.

Reference: https://developer.android.com/privacy-and-security/keystore

Focused check: `python3 android/vr/pico/tests/device/test_native_security.py`.
JNI/contract check: `python3 android/vr/pico/tests/device/test_account_jni.py`.
