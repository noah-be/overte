# Phone SH-005 local callback binding

Current domain-auth-visibility/v001 (source
1869526c6562cdf185da9ff82090635c081e98c5, manifest
ab16bb59390a3440b077bea703575ed10a65bb22594d63a7b4cfd5d3ccd1f11c)
adds the actual DomainAccountManager receiver to the same original publisher.
Phone's actual submit/URL-entry test now checks its domain-auth forwarding
boundary equals the NodeList/discovery state at every existing observation.
The full original manager/header/moc test separately checks real request-bound
background cancellation, no hidden POST or automatic resume, cross-thread queued
delivery, cache/token invalidation and the actual 15-second deadline. No native
observer rewrite or second visibility source is introduced.

The reported HTTP fixture prerequisite is resolved by the exact published
sh005-http-diagnostics-fixture/v001 delta (source
b8d426a14a161b9faf2576c6a13c0c6b9c80cfc2, manifest
f45ef9e73952ae4f68b907d9de6fe8a6866d7e9b9a7b999c026dd5c150dac38b).
The original Shared HTTP test now passes all three methods in 5.330s, including
actual sendRequest, Qt abort, UUID session and stale callback assertions. Only
the released original SafeDiagnostics.h include was added; no fixture stub or
assertion was removed. Checkpoint07's earlier compile error remains historical
evidence, not retroactively relabeled PASS.

The 2026-09-06 finite batch also imports matching Main/Phone/Pico Account
reentrancy, direct token-import, provider-receiver and persistence-context v001
deltas. AccountManager's bool setAccessTokens signature and the actual
Application::forceLoginWithTokens caller are imported together. Invalid input
cannot write the keep-login preference; context/owner changes stop subsequent
completion actions. Protected persistence failure invalidates before authRequired.
Original complete-method Qt tests pass with explicit storage/settings/provider
boundaries. Native protected-store durability, already-entered actions,
same-context request ordering and full foreground/UI acceptance remain pending.
Checkpoint08 records exact source/manifest/import pins and focused results.

Pinned v001 source 4366b47681ad3b8fbed5c793c2f1a9b7ce89ec34, manifest
d84b2d80ffa80480deed4682b46a62576830806601a49af636e5272a9ad876d0.
The published Shared patch is imported separately, unchanged, followed by
lifecycle/v002's actual Qt initial-state seed and inactive correction. The later
visibility-inputs/v001 contract supplies one out-of-line input owner for the
existing applicationGate. Phone publishes observeNativeVisibility(foreground):
Qt active is required, and an observed native background is an additional veto.
Neither observer can override the other's inactive state. Shared publishes the
same effective Gate state to the actual AddressManager HTTP request scope and,
with nodelist-visibility/v001, NodeList's atomic client-transport entry fence.
Discovery-visibility/v001 additionally forwards this same effective input from
the actual NodeList setter to DomainHandler's discovery generation. Its source
6026087a7942c224ac0086ece436cb61f5302ac1 and manifest
83c72c242b095114af7db65739faa3b793fe668d0850483f50a62cad63575b8b
are imported unchanged after ICE-hostname/v001 and Domain-diagnostics/v001.
The startup seed is after both dependency installations. Phone's actual native
observer is unchanged; no new callback signature or second visibility input.

PhonePendingNavigation wraps only its local pending value; Shared owns the
lifecycle state/generation. Native URL submission captures that generation and
delivery discards inactive/stale work. A background event clears Phone's pending
URL immediately; Java also clears its not-yet-handed-off URL on pause/destroy.
A newer explicit onNewIntent can create a new pending request; ordinary resume
does not restore the old one. Existing Qt canAcceptURL/acceptURL remains the
navigation authority, and AndroidHelper still controls load-complete ordering.
Saved-instance and history launches also discard the old internal URL; only
a fresh launch or explicit onNewIntent supplies a new navigation request.

Foreground transport now observes JNI's accepted result and retries at most
120 times at 250-ms intervals while native startup is unavailable. A replacement
visibility event resets that local transport budget, not Shared's network retry
budget. Stale acknowledgements cannot mark a newer background event foreground.
Foreground handoff acknowledges native queue ownership, not an applied Qt receipt.
The URL JNI entry separately reads the original thread-safe Gate snapshot before
taking ownership. While Qt is not yet active it returns false, preserving Java's
existing bounded latest-URL retry. An accepted URL captures the generation before
queueing and compares it again on delivery: intervening suspend/resume cannot
revive stale work. The downstream local queue checks the same Gate independently.
Destroy removes queued Java retries. Existing JNI and AndroidHelper transitions
are preserved; no duplicate common state engine or native singleton is added.

Focused checks: test_lifecycle_binding.py compiles real C++ PendingNavigation
and the complete original Phone submit/URL JNI entry bodies with Shared publication,
the actual NodeList setter/atomic field, real Qt objects and original Gate/RequestScope.
Only dependency lookup, HTTP/DomainHandler
forwarding, JNI string conversion and AndroidHelper actions are substituted.
Three methods cover early-URL retry, real queued URL delivery and generation
invalidation across suspend/resume, both observer orders, local URL cancellation,
duplicate and stopped-state behavior, including equal NodeList transport and
DomainHandler discovery receiver values,
plus source-entry assertions. Original Shared tests additionally exercise real
queued cross-thread publication. The existing Java transport checks (44 API26/35
tests) are unchanged. None is a full native build, Android JNI runtime or device proof.

The wrapper deliberately does not fake begin/connected/lost/timeout calls or
invent URL identities. SH005 http-cancellation/v001 plus required v002 now bind
the actual Shared AddressManager HTTP requests through RequestScope/RequestTicket
to AccountManager's original sendRequest/reply callbacks and owner-thread abort
timer. Shared setup uses qualified QGuiApplication::applicationState(); later Qt
activeChanged forwards its Qt input to the same arbiter. Three original real Qt HTTP/callback/startup
checks and three original lifecycle/body checks pass with synthetic network I/O.
The 20-ms timer interval is requested scheduling, not an observed stop deadline.

NodeList's six actual check-in/ICE/hole-punch/keep-alive entry paths now return
while the same effective client visibility is false. Two original tests compile
the atomic setter/state, five original entry fragments and complete keep-alive
method with explicit packet/node boundaries. They also check startup ordering.
Two Shared real queued-publication methods and three Phone actual submit/URL
entry methods pass; the latter include NodeList's actual forwarding setter and
assert its atomic state matches the discovery receiver boundary. This is not cancellation of
an already-entered send. Existing timers may run again after foreground; stale
replies, generation-bound retries and transport queues remain open work.

The unchanged scoped-hostname/v001 contract additionally binds DomainHandler's
direct QHostInfo lookup: hardReset invalidates before reset observers, and stale,
duplicate or reentrant resolver completions cannot enter the socket setter.
Its two original Qt/helper/caller checks pass in isolated network namespaces;
best-effort OS resolver abort is not a physical deadline or full DNS coverage.
ICE-hostname/v001 adds an owned ICE lookup and cancels both owners before reset
mutation, preserving numeric fast paths and the original asynchronous IPv4 policy.
Discovery-visibility/v001 invalidates both lookup generations immediately when
the effective foreground input changes; cancellation/current-target restart runs
in DomainHandler's Qt thread. Hidden target changes start no DNS, numeric ICE
completion stays closed while hidden, and stale queued visibility actions are
rejected. Duplicate foreground input does not restart work. Original complete
visibility/launch/ICE bodies with real Qt cover these paths; resolver/socket/
receiver/reset-tail boundaries remain explicit. Already-entered callbacks and
other transport work are not stopped by this generation fence.
PX16 address-diagnostics/v001 closes all 19 direct AddressManager diagnostics
and removes raw destinations from four activity arguments, without changing
navigation URLs or ordinary 404 outcomes. Two original raw-capture/Qt methods
pass. NodeList and DomainHandler direct diagnostic releases additionally close
their actual payloads while preserving legitimate application data. Other
network/third-party/OS/export/retained sinks remain outside these slices.

Actual Shared NodeList/ICE/UDP attempt tickets, remaining domain-transport cancellation,
bounded network timeout/retry execution, audio FIFO reset,
typed traces and informed equal-decline entity-script consent remain General
work. Effective Gate/HTTP/NodeList/discovery input arbitration is now bound; render/audio visibility
is not silently equated with this input. This is not device-verified recovery.
The Phone cancellation above covers unconsumed local URL work; the newly imported
Shared behavior additionally cancels scoped HTTP/direct/ICE-DNS work, not the entire domain
connection, audio stream or JavaScript evaluation.

Entity-default-deny/v001 additionally denies client entity load/content callbacks
before fetch/compile/preload. This is denial-only, including local/avatar entities,
with a closed error status; no consent dialog/grant path or finite revoke backend
exists yet. Actual Shared full-client/entity-renderer constructors use the fenced
CLIENT_SCRIPT/ENTITY_CLIENT_SCRIPT contexts. No native allow bypass is permitted.
