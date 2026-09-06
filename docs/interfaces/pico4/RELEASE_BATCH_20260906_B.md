# Pico bounded batch B — source wave35

Existing goal stays PAUSED. Import matching Main/Pico login-order/v001,
profile-context/v001, reply-cleanup/v001, settings-context/v001 through v004,
and script-info-diagnostics/v001 plus v002, in that dependency order. The exact
persistence-context/v002 and transitive chain are already sealed in wave34.
All new released source snapshots match immediately after narrow patch import.
No Phone, build recipe/lock, foreign worktree or build-cache changes.

Pico already creates AccountManager(true) after protected-store registration.
The original constructor connects loginComplete to requestAccountSettings and
the upload timer to postAccountSettings. Original Application connects script
info messages to ScriptEngines; JSConsole still consumes the internal signal.
No new native hook, settings state UI, public API clone or duplicate manager is
needed. The Pico source regression pins those existing consumers; behavioral
evidence comes from the released actual-method/class Qt tests, not that pin.

New credential intents supersede older same-endpoint replies; explicit pending
login blocks background refresh. Profile replies require current credential and
profile scopes, bounded validated content and persistence before notification.
Six reentrant reply-creation early returns now schedule deferred cleanup.
Settings lock payload/revision snapshots, serialize PUT admission, acknowledge
only exact sent revisions, retain local/same-value edits and suppress stale GETs.
Exhausted bounded GET retries restore the prior state without a false success;
a new explicit request receives a fresh retry budget. Token refresh retains
settings; accepted new account/login contexts reset them.

Five script wrapper/shutdown public Qt sinks use closed Redacted events while
preserving internal console/entity/server payloads and original severity. This
does not sanitize internal console contents or other direct diagnostic sinks.
Default-deny entity scripts are still unavailable pending informed consent and
finite revocation; no grant or termination implementation is claimed here.

Targeted original Qt tests cover snapshot concurrency/clock exhaustion, manager
GET/PUT/retries/header compilation, login/profile ordering/reentrant cleanup,
direct import/persistence/completion and all five original 15-second credential
deadlines. Fixtures substitute transport/data/storage boundaries; the profile
timeout marker is not a physical profile deadline measurement. No full native,
device, signing, build or remote actions occurred.

Still open: server write ordering after uncertain abort, general manager thread/
foreground cancellation, native storage atomicity/durability/in-I/O reentrancy,
initial origin/HTTPS/token policy, total streaming bounds, optional profile
schema, complete cross-view UI recovery, wider console/evidence privacy and
all original graph/custom-control/source-payload/device acceptance gates.
The named same-endpoint ordering and settings retry issues in older reports are
resolved only to the scope above. No overall feature-parity or frozen-build PASS.

General alone integrates remotely. COMMIT_MAP in the incremental handoff marks
all nine Shared imports DO_NOT_REPLAY separately from the Pico-owned pin/docs.
