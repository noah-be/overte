# Phone protected account storage

PX-15 v001 is pinned to source 3ca00141a74d75ea94195d79880f74f8a9550016,
manifest db934a5a0b2b8bc41aefde437fb85886ea577c59cb4de4e3bbbd539ed29301ed.
Its unchanged Shared patch is imported separately from Phone-owned changes.

Production path: PhoneInterfaceActivity.onCreate prepares application-scoped
SecureAccountStore before QtActivity.onCreate. Existing QtActivityLoader calls
System.loadLibrary(main library) before startApplication; JNI_OnLoad in Phone
registers the adapter through AccountManager::installProtectedAccountStore.
Phone CMake setup_hifi_library includes these src/*.cpp through its existing
recursive source glob and already links networking. No extra CMake source list
is required for these native files.

Preparation resolves only trusted application paths; it does not read credentials
or open Keystore. The published Shared account API is synchronous, not an async
worker guarantee. Native Qt scheduling, storage latency and UI responsiveness
remain runtime acceptance work; host JNI worker attachment tests do not prove
that every AccountManager caller executes on a dedicated worker.

Java AndroidKeyStore protects a single opaque account map in noBackupFilesDir.
The JNI transport maps exceptions to the exact Shared taxonomy without rendering
them, wipes copied Java buffers, clears failed reads, and attaches/detaches native
worker threads. Shared alone owns legacy parsing, migration and quarantine.

Focused checks:

- secure-account-store-test.sh: production Java, JCA cryptography, test-only Keys.
- run-jni-storage.py: production Java and C++ transport and JNI_OnLoad, a real JVM
  with -Xcheck:jni, Shared migration coordinator, and test-only AccountManager
  registration seam. Includes worker attachment, missing key, unavailable key,
  corrupt record, I/O failures, verified migration, quarantine and logout.
- The same runner compiles/runs the pinned Shared coordinator conformance test.

These are host checks, not AndroidKeyStore or Qt AccountManager runtime evidence.
Pending: full native/Java packaging and Qt caller compilation, device startup,
locked store, keystore invalidation, reinstall/orphan handling, process interruption,
upgrade migration, retained plaintext/output scans, and all PH/PX acceptance gates.
No native app build, emulator, hardware, signing or release is run here.

## Closed Phone diagnostics

PX-16 v001 is pinned to 6f11d1bedf620b39a0c05d93e27fed64b85b1208,
manifest 203f5a8498989f40f5f2760282960ed78b16b62d4e624d618de601a34688c52b.
Phone RedactingDiagnostics imports the original Shared SafeDiagnostics Java
source. StoreException and permission callback callers emit closed events only.
The only Phone Java log sink is fixed-tag Log.println; no Throwable/context is
forwarded and an unavailable sink drops output. Native JNI failures discard
Throwable objects without formatting; the imported Shared Qt handler sanitizes
active stdout, logcat, file and shutdown output.

run-redaction-contract.py runs original C++/Java conformance. The focused launcher
runner also runs RedactingDiagnosticsRobolectricTest on API 26/35, exercising
actual Log calls and storage/permission callers, including canary strings.
Phone Gradle includes the original security/redaction/java source after General's
explicit px16-android-host/v001 ownership release (manifest
7732403a83709cc8778ec8ad72dc60aeafb914d41377e2dc9cad7ab881aebd03).
The accompanying Shared host source includes were imported preserving the Phone
base's additional qtJava/PhoneInterfaceActivity entries; only patch context was
reconciled, no extra Shared behavior was implemented by Phone.
Startup/direct third-party logs, crash/export captures, screenshots and retained
output scans still need Shared/platform integration and device acceptance.
