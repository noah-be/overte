# Request-bound domain cancellation and recovery

DomainAccountManager::requestAccessToken now returns its existing opaque
RequestTicket; callers that ignore the result remain source-compatible. Its
new loginRequestFinished(request, context, outcome) signal separates Succeeded,
Failed, Cancelled, TimedOut and ResponseRejected. Legacy manager complete/failed
signals remain for other consumers. Cancellation is emitted only for a genuinely
owned pending reply, after invalidation/clear/abort. The post-invalidation
context ticket is captured BEFORE abort can invoke external callbacks.
The normal response result uses its original context; real15s timeout and
oversized streaming response use their new post-abort context. Raw reply data,
URLs, credentials and IDs are not included in this signal.

RequestTicket::sameRequest compares the same nonzero opaque scope/generation,
even after cancellation. It does NOT make an invalidated ticket current.
Default/unscoped tickets never match. The original current/snapshot/HTTP/DNS
semantics are otherwise unchanged. Import this actual updated header too.

LoginDialog stores the returned request ticket and receives outcomes using
Qt::QueuedConnection, after its synchronous caller returns and QML loads the
progress view. It matches request identity, checks current context for all
non-cancellation outcomes, and consumes the ticket before emitting a UI event.
Old/duplicate outcomes cannot clear or close a newer request. A reopened domain
dialog can observe the manager's existing pending ticket; non-domain dialogs
do not claim it. Inactive/exhausted admission gets a deferred fail-closed UI
failure without a live reply and without clearing a newer active request.
Account observers/admission retain the preceding pending-ownership contract.

Actual LoggingInBody.qml has a separate domain failure handler. Timeout gets a
connection/retry message; other failures do not assert incorrect credentials.
Cancellation stops spinner/glyph and uses existing dismiss/tryDestroy routes,
not a retry form against a newly selected domain. Failure/timeout loader payload
retains the same loginDialog; actual LinkAccountBody's readonly domain selection
and domain name are sourced from that dialog's existing getters. No automatic
retry, credential persistence or URL text is added. Account/social handlers
remain unchanged. No competing platform error schema or private ticket reaches
QML; only closed reason strings cancelled/timeout/failed are emitted there.

Focused proof uses ALL original manager methods/header with real Qt/moc/replies,
including actual15s timer and emitted request/context/outcome correlation.
Complete original UI constructor/loginDomain, original QML handlers and real
QQmlEngine Connections exercise success/failure/timeout/cancel, duplicate/old
queued outcomes after a new request, and timeout followed by a context change.
Inactive admission uses an explicit transport fixture; not a forced2^63 runtime
exhaustion. Loader, full visual dialog dismissal and network transports remain
declared boundaries. Existing credential/getter/raw-log tests remain intact.

Requires matching sh005[-apple]-login-pending-ownership/v001, auth/v003 and their
complete prerequisite chain. Import both manager files, RequestCancellation,
both LoginDialog files, actual QML and listed tests together. No platform-owned
source or frozen SH001 build input changes. Select the separate retained Apple
variant; do not replace its Phone OR iOS guards with Main's Phone-only guards.

Still pending: full Qt5/native/HMD/UI loader/dismiss integration, UI-thread
affinity, AccountManager target/generation behavior, global foreground and
consent, initial origin/TLS/expiry/refresh policies, full cross-view navigation
semantics and original artifact/node gates. This is not whole application proof.
