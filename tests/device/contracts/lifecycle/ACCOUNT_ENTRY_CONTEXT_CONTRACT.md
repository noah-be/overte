# Account entry points and synchronous reentrancy

Actual AccountManager::setAuthURL retains a RequestScope ticket and QPointer
through settings reset, account-map loading, diagnostics and outward callbacks.
After failed protected loading, authRequired may synchronously log out, change
endpoints or destroy the owner. The superseded invocation must not then start
profile/token work or announce an endpoint. The loaded endpoint is announced
before starting requests: those intentionally acquire a new credential generation.
A reentrant endpoint listener also fences subsequent work. Login completion and
profile/refresh continuations retain the same checks.

Actual setAccountInfo similarly stops after a reentrant profile startup or
settings reset. This is the existing credential-generation policy applied to
these two entry points, not a new protected-storage format or native adapter.

The existing Qt/moc account-context fixture now extracts both complete production
methods alongside real request/completion methods and the real RequestScope.
It checks failed-load logout/replacement endpoint counts, deletion during re-auth,
profile-start logout/deletion, and normal refresh endpoint notification. Storage,
settings, account value and profile startup remain explicit test substitutes;
network requests use local replies in a network-isolated process. The former
actual source fails the endpoint-count assertion. Positive deletion cases do not
constitute a general memory-safety proof or full AccountManager native compile.
Native protected-store persistence, restart tombstones, hardware/platform login
and original39 acceptance remain open.
