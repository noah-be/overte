# SH-005 actual HTTP lookup cancellation

Implementation-only, narrow continuation after lifecycle/v002. This is real
HTTP work cancellation, NOT completion of domain transport, retry/recovery UI,
entity consent or SH-005 acceptance.

The actual full-client Application_Setup installs the AddressManager visibility
policy immediately after creating it; Application::activeChanged forwards later
observations. The C++-only setter is NOT a QML/script slot. Assignment clients do
not install this foreground policy. Duplicate visibility does not invalidate
work. Initial inactive observation is not mislabeled as a resume. After leaving
foreground, previous API retry state is cleared and automatic refresh/startup
lookups stay rejected until a new existing explicit lookup trigger. Visibility
alone does not restart an HTTP request. This does not attest that a script's
UserInput enum came from a human; informed entity-script consent remains open.

Actual AddressManager API callbacks now carry RequestTicket values from one
instance-owned RequestScope. Every new HTTP lookup supersedes the prior one;
accepted direct IP/DNS, relative-path and serverless navigation also invalidate
prior HTTP responses. Tokens contain no URL/user/device identifier. Atomic
generation changes preserve exact request identity across thread-queued sends;
exhaustion/destruction fails closed. Inactive requests never reach network I/O.

The original AccountManager::sendRequest checks the captured ticket before
creating a QNetworkRequest, before accepting session-header state and before
dispatching success/error. QNetworkReply has a real owner-thread QTimer observer
which calls abort() after observing cancellation. 20ms is its requested check
interval, NOT a measured/hard OS abort deadline. Late AddressManager handlers
also check the reply ticket before changing address/history/retry state.

Receiver destruction invalidates the ticket BEFORE abort(): QObject::destroyed
can run while old finished connections still exist. The targeted original-body
test found and now covers this reentrant callback hazard. Reply deletion stays
after callback processing; a destroyed receiver aborts/releases its orphan.
Other AccountManager operations retain explicitly unscoped behavior.

Phone/iOS use the actual Shared Setup/Events callers. Pico must add exactly:
`DependencyManager::get<AddressManager>()->setClientLookupVisibility(QGuiApplication::applicationState() == Qt::ApplicationActive);`
immediately after its existing `DependencyManager::set<AddressManager>();` in
the full-copy Application_Setup override, until SH-011 removes that override.
This is a narrow released native startup hook, no duplicate lifecycle singleton.

Required v002 migration: v001 omitted the QGuiApplication qualification in this
free-function startup scope. Import the v002 Shared correction and replace the
same one line in the Pico-owned startup override. The later Application member
activeChanged seed is unchanged. A focused real Qt6Gui compile of the original
startup line reproduced the v001 error and passes with this correction; full
platform compilation remains pending. Earlier v001 release bytes stay immutable.
All other released changes are Shared-owned and imported together. The existing
lifecycle test receives only a new AddressManager boundary, preserving execution
of the ORIGINAL Application::activeChanged body.

Focused tests compile the actual RequestCancellation header, ORIGINAL complete
AccountManager::sendRequest method, original callback class/constructor and
original AddressManager visibility/callback-parameter methods against real host
Qt6 Core/Network/moc. Only surrounding application owners and the network I/O
createRequest boundary are test substitutes. They check zero I/O for stale
queued requests, actual timer-driven abort, late callback/session suppression,
receiver destruction/reentrancy, normal/unscoped callbacks, initial/resume and
duplicate visibility, queued cross-thread visibility and concurrent ticket
uniqueness. The existing three lifecycle gate/actual-event tests remain required.

Pending: full Qt5/Qt6 platform compilation, bounded domain DNS/UDP/NodeList
check-in/reconnect behavior and its binding to the higher-level lifecycle Gate,
canonical URL duplicate intent policy, connect/retry deadlines, recovery UI and
exportable typed trace, entity-script consent/finite in-flight revoke, and real
physical timing/resource/focus observations. The existing Gate is not claimed
Connected, and no timer interval or host boundary test proves physical stop.
