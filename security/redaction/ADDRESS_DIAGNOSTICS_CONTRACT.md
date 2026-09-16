# PX-16 direct Shared address diagnostics

IMPLEMENTATION ONLY. Requires px16-redaction/v001's exact SafeDiagnostics.h
and sh005-http-cancellation/v001+v002 when importing this AddressManager delta.
No new events, native API or platform-owned edits.

All 19 remaining direct Qt diagnostic expressions in AddressManager now pass
exactly one closed diagnosticEvent constant, with no URL, host, port, domain ID,
location map/path, shareable name or QNetworkReply errorString argument. Original
debug/warning categories and severity remain. Malformed addresses use
UrlRejected; API/disconnected-save errors use ConnectionFailed; informational
attempts use Redacted, never ConnectionReady without a real connection.
No sensitive argument is evaluated merely to sanitize it later.

Four existing wentTo activity calls retain their closed trigger/type, but their
destination argument is a fixed OVT_REDACTED. The inspected UserActivityLogger
logAction currently returns without transmission; this does NOT claim an active
telemetry leak was observed. Removing raw destinations at its callers prevents
these four sites from supplying private URLs if that sink later changes.

Tests compile/run all original logging expressions against actual Qt logging
categories with a capture handler that does NOT sanitize the input. The original
complete AddressManager.handleAPIError body is also compiled with real Qt reply
and cancellation objects; a canary-bearing 404 still clears retry state and
emits the existing not-found/finished outcomes, while a stale response emits
nothing and makes no new state changes. Only surrounding AddressManager signal
counters are substituted. The four activity arguments have a strict source
check. These are focused source/caller checks, not a full networking library.

Still pending: direct NodeList/DomainHandler/UserActivityLogger and other Shared
callers, frequency/third-party stdout, early dynamic Qt metadata, native crash/
screenshot/export and retained artifact canary scans. Existing active client Qt
handler drops dynamic context per v001, but this slice does not prove all startup
or server sinks do so. It does not change actual connection URLs, saved navigation
settings/history, API requests, domain signals or consent. No PX-16/node PASS.
