# Account login completion continuation

SH-005, implementation cohort #685. Additive to account-auth-context/v001:
Main fa3abe7fd0ac329f0f3392b4237eb0cf3e196ad3 or Apple counterpart
f236051044833b1186a192ee0fc978538acb6358 and their pinned prerequisites.

The actual `requestAccessTokenFinished` success branch captures its existing
credential-context ticket and a QPointer to AccountManager before any outward
completion boundary. With account-persistence-context/v002, persistence and its
guard precede `loginComplete`; reported store failure cannot emit success.
After signal delivery, it stops before profile work if a receiver destroyed the
manager, logged out or changed the auth server. Both boundaries retain the guard.
No field is dereferenced through a destroyed manager to perform that check.
Duplicate-finished suppression is unchanged; persistence-before-success ordering
is now intentional and checked by the corresponding updated fixture.

This does not roll back persistence already entered before a callback invalidates
the context. Logout's original erase operation remains responsible for its own
storage semantics. It does not cancel a profile request that already started.
`setAccessTokens` is covered separately by token-import and persistence-context/v002.
Account-login-order/v001 adds same-endpoint credential-intent supersession and
refresh admission; see ACCOUNT_LOGIN_ORDER_CONTRACT.md for its exact scope.

The original context fixture executes complete real logout, auth-server change,
password POST and finished methods with real Qt signals/RequestScope. Added tests
cover immediate logout/server replacement/destruction during loginComplete and
the explicit persistence boundary, checking no following profile work. Existing
ABA, same-server no-op, stale replies, refresh and reentrant POST assertions are
retained. Completion payload/refresh/bounds/cleanup tests still run unchanged,
apart from adding the real context field to their declared owner boundary.

Pending: full storage/native/provider and thread/lifecycle integration, actual
foreground UI cancellation, profile response ownership, initial origin/token policy,
streaming memory and original node/artifact acceptance. This
later source is not qualified by the separate frozen cold-build SHA.
