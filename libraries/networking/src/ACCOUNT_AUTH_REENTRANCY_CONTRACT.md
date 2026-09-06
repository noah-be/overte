# Account login completion continuation

SH-005, implementation cohort #685. Additive to account-auth-context/v001:
Main fa3abe7fd0ac329f0f3392b4237eb0cf3e196ad3 or Apple counterpart
f236051044833b1186a192ee0fc978538acb6358 and their pinned prerequisites.

The actual `requestAccessTokenFinished` success branch captures its existing
credential-context ticket and a QPointer to AccountManager before emitting
`loginComplete`. After signal delivery, it stops before persistence/profile
work if a receiver destroyed the manager, logged out or changed the auth server.
It repeats the same check after persistence before beginning the profile request.
No field is dereferenced through a destroyed manager to perform that check.
Normal successful login order and duplicate-finished suppression are unchanged.

This does not roll back persistence already entered before a callback invalidates
the context. Logout's original erase operation remains responsible for its own
storage semantics. It does not cancel a profile request that already started.
`setAccessTokens` is a separate caller and is not changed by this delta.
Concurrent latest-request ordering in one unchanged context is still unresolved.

The original context fixture executes complete real logout, auth-server change,
password POST and finished methods with real Qt signals/RequestScope. Added tests
cover immediate logout/server replacement/destruction during loginComplete and
the explicit persistence boundary, checking no following profile work. Existing
ABA, same-server no-op, stale replies, refresh and reentrant POST assertions are
retained. Completion payload/refresh/bounds/cleanup tests still run unchanged,
apart from adding the real context field to their declared owner boundary.

Pending: full storage/native/provider and thread/lifecycle integration, actual
foreground UI cancellation, same-context ordering, initial origin/token policy,
streaming memory, setAccessTokens and original node/artifact acceptance. This
later source is not qualified by the separate frozen cold-build SHA.
