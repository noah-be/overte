# PX-16 direct NodeList diagnostics v001

Requires px16-redaction/v001 SafeDiagnostics.h only; no native hook or dependency
on unrelated v09 runtime changes. Actual NodeList.cpp now emits only the closed
Redacted event at all52 direct Qt diagnostic expressions. Usernames, node/session
IDs, machine fingerprints, domains, sockets, paths, gains and dynamic timing
values are not passed to these sinks. Existing debug/warning severity and
categories are retained; legacy qWarning(networking) is expressed as the proper
category-aware qCWarning(networking). Existing default-category calls stay so.

The one HIFI_FCDEBUG throttled caller keeps its original frequency behavior and
now receives a QString built from the same closed event. Its payload is checked
at source; the full frequency logger/backend is not executed by these tests.
Unused debug-derived enum/skew/lag values are removed; packet reads, actual
connection paths, protocol fields, state changes and signals are unchanged.
A one-time normalized source comparison against base2c60b810997cf103cfe075fe673c711860d10a4e
confirmed no other nonlogging token changes beyond those documented removals.

Two focused tests PASS1.342s: all52 original expressions compile/run with real
Qt and an unsanitized raw capture handler; the original complete
processUsernameFromIDReply executes with a test-only ReceivedMessage boundary
and preserves canary username/node/fingerprint/admin signal data while logging
only OVT_REDACTED. No full NodeList/networking or device suite was run.
An initial test-only counter name collided with Qt's signals macro; corrected
to signalCount before the passing build. No production API changed for this.

Pending: other Shared and native sink paths, DomainHandler/LimitedNodeList,
third-party/early Qt metadata, crash/screenshot/export and retained artifacts,
full networking Qt5/Qt6/platform compilation and original PX-16 node acceptance.
This does not redact legitimate application data or claim whole-process privacy.
