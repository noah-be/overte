# Account profile response ownership

SH-005 / PX-15, cohort #685. Additive to matching account-login-order/v001
(Main d1786f79fc486fb2e0267c9f99fba8254f34592b or Apple
c51ea5567b3574803c4b1e5309ee3095723cc882) and its full prerequisites.
Import AccountManager.cpp AND .h (new private profile RequestScope) with fixtures.
No public method or platform hook changes.

Actual requestProfile denies startup while explicit login is pending, snapshots
credential intent and begins a new profile generation. Both tickets are observed
in the reply's Qt event loop; completion requires both exact current-owner scopes.
Logout/server/login/refresh invalidation or a newer profile request therefore
cannot let an older profile overwrite account data. Missing/foreign tickets and
duplicate completions are rejected. Actual reply cleanup uses deleteLater.

Bearer GET uses manual redirects and the existing15s deadline helper. Completion
requires untimed-out/error-free2xx JSON object, at most1MiB terminal read with no
remaining bytes, success status and nonempty string data.user.username. This
preserves optional profile fields and existing data setter semantics. It does not
validate every optional field or bound total framework streaming allocation.

Persistence precedes profileChanged and usernameChanged. Reported persistence
failure invalidates credentials in the prerequisite implementation; continuation
checks owner plus both contexts after persistence/profileChanged, so destruction
or replacement cannot publish the following username signal or dereference the
destroyed manager. Already entered native I/O is not rolled back by these guards.

Fixture executes complete original GET/completion/error methods and the original
RequestScope/Qt/moc, with network transport/account data/storage explicitly bounded
as fixtures. Baseline stale credential response incorrectly persists/publishes.
Positive current response, duplicate suppression, both latest-profile reply orders,
nine malformed/status/network/size/timeout/missing-ticket negatives, cleanup and
reentrant profile/persistence replacement/destruction are tested. Timeout-negative
sets the marker; it is not a measured15s profile socket/OS deadline assertion.

Remaining: native/thread/foreground/full-client acceptance, authenticated initial
origin, total streaming allocation, optional data schema, account settings/locker
and other callbacks, actual persistence durability/reentrancy, full typed UI
recovery and original node/artifact gates. Frozen build source is unchanged.
