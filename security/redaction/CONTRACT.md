# PX-16 closed diagnostic events v001

Status: CONTRACT_READY_FOR_IMPLEMENTATION, not PX-16 PASS. C++14 header
`security/redaction/SafeDiagnostics.h`; Java 8-compatible source
`security/redaction/java/org/overte/security/SafeDiagnostics.java`.

## Sink interface

C++/Objective-C++: `overte::security::diagnosticEvent(DiagnosticEvent)` returns a
static `const char*`. `sanitizeDiagnostic(const char* bytes, std::size_t size)`
returns a static closed event constant and never retains the input. Pointer must
be valid for the declared length; null is accepted as redacted. Both are noexcept.
Java: `SafeDiagnostics.event(SafeDiagnostics.Event)` and
`SafeDiagnostics.sanitize(String)` return only closed event strings. Null/unknown
input becomes `OVT_REDACTED`. C++ enum names are CamelCase, Java UPPER_SNAKE_CASE;
wire outputs are identical `OVT_` codes declared in the two source files.

Owners bind the actual native sinks (Phone/Pico RedactingDiagnostics.java and
iOS RedactingDiagnostics.mm), including native exception paths, to these
functions. Include the original Java source in the product's source set or
import the release path; do not fork a second sanitizer. Never forward exception
objects, raw context, dynamic tags, paths, stack traces or the original payload
alongside the sanitized return. Use constant tags and fixed severity labels.
Output is <=32 ASCII bytes. There is no mutable allowlist or release-mode bypass.
Select an event enum from control flow, never by interpreting sensitive values.

This deliberately preserves structured outcomes, not arbitrary free text.
Every non-exact event string becomes `OVT_REDACTED`, including encoded, split,
prefix/suffix, concatenated, whitespace-extended and embedded-NUL messages.
No regex can guarantee unknown credential removal while retaining arbitrary
text. Add a useful event only through a new pinned version and reviewed caller.

## Sensitive taxonomy and sinks

Credentials include access/refresh tokens, passwords, keys and cookies.
Private network context includes auth URLs, private targets, query strings and
referrers. Identifiers include user/session/device/account/domain IDs, filenames,
native error descriptions and stack paths. All such values and their reversible
fragments are prohibited in stdout/stderr, log files, JUnit, screenshot captions,
crash attachments and export text. The sanitizer produces text for these sinks;
it does not inspect pixels, third-party crash reporters or existing log files.
Screenshots and actual retained outputs need separate downstream canary scans.

## Production binding and checks

Included AccountManager patch removes token prefix/suffix logging. Included
Application.cpp patch feeds only closed text to active stdout, Android logcat
and FileLogger sinks, discards dynamic QMessageLogContext, and keeps shutdown
logging fail-closed without touching a destroyed FileLogger. It bypasses the
general LogHandler's dynamic ID/context decoration on this client path.
This release does not rewrite server logging or direct third-party stdout.
Early startup before Application's installed handler, repeated-message direct
LogHandler paths, native sinks and crash/export capture are still audit work.

Compile/run `tests/device/contracts/redaction/sanitizer-test.cpp` with C++14.
Compile this Java source plus `tests/device/contracts/redaction/SanitizerTest.java`
to isolated scratch and run SanitizerTest. Both test the production sanitizer,
closed positive events and canary negatives across seven abstract sink labels.
Abstract sink repetition is not native sink or screenshot evidence. Native
owners add focused actual-caller tests with this same contract. No real tokens,
device identifiers or private targets belong in fixtures or diagnostics.

Source-level prerequisite is only the included sanitizer; no storage or evidence
module import. The AccountManager patch parent also contains PX-15 v001, so apply
that first when testing the complete Shared caller stack. Full Qt client
compilation, SH-002/005/006 acceptance and artifact/device output scans remain
pending. Missing native bindings must drop payloads, never restore raw logging.
