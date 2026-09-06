# Pico PX-16 diagnostic binding

PI-002 source implementation; no artifact or privacy acceptance claim.
Pinned v001 source 6f11d1bedf620b39a0c05d93e27fed64b85b1208; manifest
203f5a8498989f40f5f2760282960ed78b16b62d4e624d618de601a34688c52b.
The unmodified Shared patch follows PX-15 in this local integration branch.

Gradle compiles the original Shared Java sanitizer source set. Pico's actual
Android sink accepts only its fixed Event enum and fixed severity functions,
uses constant OvertePico, and sanitizes before Log. Existing Activity, audio and
WebView exception sinks no longer pass Throwable, dynamic context, native thread
IDs, URL lengths or dimensions. Events without a reviewed shared equivalent are
Redacted, not a new platform allowlist. Native WebView/OpenXR loader and debug
input-layer sinks use the original Shared C++ event function; ExceptionDescribe
was removed from the WebView JNI exception path. Experimental input remains
debug-only/fail-closed; logging changes do not enable it.

Focused tests execute actual wrappers with captured Android log substitutes,
compile real Java callers against Android SDK, and execute the original Shared
positive/canary-negative corpus. They do not capture logcat or pixels. Full Qt
startup/direct/third-party logging, crash/export capture, historical output,
screenshot and actual retained-output canary scans remain General/downstream
acceptance work. No real credential or device selector is used in fixtures.

Run `python3 android/vr/pico/tests/device/test_diagnostics.py`.

## Direct Shared address callers

px16-address-diagnostics/v001 source 793b5bd141e82c6ca7c7c362b53475f77c143fee,
manifest 33301aeda6dbfa72055391e09a0385d80d98effddd13b72a82aa899c21f8588a,
is consumed as an exact Shared import after HTTP cancellation v001/v002. Pico
already uses that original AddressManager through the full-client networking
target; no native signature or startup change is needed.

All 19 direct Qt diagnostic expressions now pass one closed existing event
constant. They no longer evaluate URL, host/port, location map/path, domain ID,
shareable name or reply errorString merely for logging. Debug/warning categories
and severity are retained. Attempts do not claim ConnectionReady. Four wentTo
activity calls now supply a fixed redacted destination; their sink is currently
disabled, so this is caller hardening, not evidence of observed transmission.
Actual navigation addresses, persisted history, network requests and domain
signals are unchanged. This is not an entity-script consent implementation.

Two original focused tests compile all actual log expressions plus the complete
API-error body with real Qt and a raw, non-sanitizing capture. Canary-bearing 404
errors retain retry clearing/not-found/finished behavior; stale replies produce
no new state/log outcome. Three original HTTP tests also pass after the import.
These tests are not a full networking build or logcat/retained-artifact scan.
Other Shared DomainHandler/NodeList, early Qt context, third-party/native output,
crash/screenshots/exports, historical output and physical privacy evidence remain
separate pending criteria. No blanket PX16 acceptance is inferred.

## Direct Shared NodeList callers

px16-nodelist-diagnostics/v001 source679caae695175fb7fab2ab13a9ed698b33caf29a,
manifest22f6d321f1f4586a8ce70555116d0070447458bf2156dd6e52ba82386294ce47,
is consumed unchanged through Pico's existing networking/NodeList dependency.
No native hook or copied NodeList implementation is required. All52 direct Qt
payloads and the single throttled payload use the original closed Redacted code;
username/node/fingerprint/socket/path/gain/timing values are no longer supplied
to these sinks. Connection/protocol/state and legitimate signal data are retained.

Original52 Qt expressions plus COMPLETE processUsernameFromIDReply execute with
real Qt and an unsanitized capture: two methods PASS1.341s. Only received-message
and signal-collection boundaries are test substitutes; canary user/node/machine/
admin values still reach the signal while logs contain only OVT_REDACTED.
The throttled payload is source-checked, not its real backend/frequency behavior.
Whole NodeList/networking/platform compilation, DomainHandler/LimitedNodeList/
other sinks, retained artifacts and real physical privacy criteria stay pending.
