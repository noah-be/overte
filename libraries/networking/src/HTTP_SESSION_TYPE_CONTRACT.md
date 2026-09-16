# SH-005 actual HTTP session owner type correction

The original AccountManager.h declares QUuid _sessionID on both main and Apple.
The earlier focused fixture incorrectly substituted QByteArray. Restoring the
actual declaration reproduced a real Qt6 compile error in main's complete
sendRequest body: assignment of QByteArray to QUuid. Main now explicitly parses
the header as QUuid, matching the existing Apple implementation. Qt5/full
networking compilation remains pending; no production session type changes.

Both tests now compile the exact original field declaration extracted from the
production header, not a rewritten fixture type. A valid current header updates
the UUID; a stale generation and destroyed receiver cannot overwrite the initial
UUID. The original full request/callback/visibility methods and real Qt abort/
timers/concurrency tests remain intact. Network request creation, account object
and callback receivers are boundaries, not OS transport/whole-client proof.

Requires sh005-http-cancellation/v001+v002 and their existing pinned source
prerequisites; current visibility-inputs source hook is already consumed by all
owners. Import both test files together. Apple already has the exact production
conversion and consumes the separate test-only delta; remove its old temporary
type-rewriting wrapper in platform-owned tests rather than modifying this test.
Malformed-current UUID header behavior is unchanged (Qt null UUID), not a new
protocol validation or authentication policy. Full retry/recovery/in-flight
deadline/other network queues and original SH005 acceptance remain pending.
