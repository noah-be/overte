# Pico lifecycle integration — revision 09 source checkpoint

v002 migration: source 359adacc3f726699164ce521fd23608214122cbe, manifest
24f7b34b021cbb92d4fc38030f08780b1e2bfebc6daa09f21434c788634a6c5b.
Its CONTRACT.md explicitly releases one Pico override line: immediately after
the state-signal connection, call `activeChanged(applicationState());`. The
current Qt state now seeds the same instance even if no later signal arrives.
Shared also clears `_isForeground` on ApplicationInactive. State API is unchanged;
duplicate observation is idempotent. Keep this tiny hook delta separate for
SH-011 review. Original production event body is exercised with test-only Qt
boundaries, not a full Qt run or proof of actual network/audio cancellation.

PI-003/005 consume General SH-005 lifecycle v001, source
4366b47681ad3b8fbed5c793c2f1a9b7ce89ec34, manifest SHA256
d84b2d80ffa80480deed4682b46a62576830806601a49af636e5272a9ad876d0.
The authoritative interface and behavior remain
`interface/src/ApplicationLifecycle.h` and the immutable released CONTRACT.md.

The existing Pico override connects `Application::applicationStateChanged` to
`Application::activeChanged`. Pico builds the original Application.cpp and
Application_Events.cpp into the full interface target; only Application_Setup.cpp
is replaced. Therefore the published Qt visibility caller reaches the original
out-of-line applicationGate instance. The early-loaded picoOpenXR library does
not define a second instance or link the full client just to obtain that symbol.

The lifecycle v001/v002 gate itself implements observation/generation, not the
side effects of a Cancel action. Actual HTTP cancellation is now supplied by the
separate contract below. No platform reconnect timer, entity-script consent
policy or acceptance trace is invented here.
Pico's Java Activity focus/resume enforcement still independently closes local
input/audio eligibility. It does not impersonate a Shared network cancellation.

Remaining General bindings: domain DNS/UDP/NodeList generation-bearing async
callbacks/cancellation and lifecycle Gate state, canonical duplicate-intent
policy/retry/deadlines/recovery UI/typed trace; actual default-deny consent and
safe in-flight script revoke. Shared audio mute/PCM clear/late-focus retry is now bound through the
separate sh006-pico-audio/v001 release and real Java consumer; its full Qt/device
proof remains pending (see android/vr/pico/docs/AUDIO_LIFECYCLE.md). If a native foreground
callback is added, it must reach the same full-client instance with explicit
Qt/native-focus arbitration and safe pre-initialization handling, not overwrite
another observer's denial or dereference a not-yet-loaded interface DSO.

Focused proof: original Shared C++14 state/order/retry/clock/concurrency tests;
Pico source tests for the real override signal connection, original event target
and singleton ownership. Full Qt/native link, controlled network loss/resume,
script consent/revoke, actual headset focus and end-to-end stop remain pending.

## Actual HTTP cancellation binding

Required v002 source fbed0123185731aafa84129b4ae5f4d85789c09a, manifest
aeccfa039e24edde28dfa7b9781de6a0f04b9e49495da6a446271dc27f683eef.
Pico's real Qt6Gui/free-function syntax regression exposed v001's unqualified
applicationState() call. General reproduced it and released the qualified
QGuiApplication::applicationState() correction in Shared and the exact Pico
startup hook. Both are consumed; the original regression now passes. The later
Application member's initial activeChanged seed remains unchanged. v001 alone
is not an acceptable source prerequisite; retain this correction during replay.

sh005-http-cancellation/v001 source adea0552f0feca4baeba1c2e7bb343930253ded9,
manifest 488338597e387976e9a137472c679f4996967c6f14cfcb69992b860647b78233.
All Shared deltas are imported together. The explicitly released one-line
Pico startup hook c1595c3eb2 originally installed current Qt visibility after
AddressManager; it is superseded by the combined-input and NodeList seed moves
documented below. Keep each exact released hook separate under SH011. Later observations reach the original Application Events
caller; no extra Pico/early-DSO scope or singleton is created.

Original AddressManager requests carry actual RequestTickets. New lookups and
accepted direct/relative/serverless navigation invalidate older HTTP work.
Inactive requests fail before send, session-header processing and success/error
callbacks reject stale tickets, and real owner-thread reply timers call abort.
Receiver destruction invalidates before abort can synchronously finish a reply.
The 20ms observation interval is not a hard or measured physical stop deadline.
Resuming visibility does not recreate an old request; a new existing explicit
lookup trigger is required after foreground loss. Script-visible UserInput is
not authenticated human consent. Other account requests remain unscoped.

Two original Shared HTTP tests compile the actual sendRequest/callback class,
AddressManager policy methods and ticket header with real Qt6 Network/moc, using
only network creation and surrounding owners as test substitutes. They exercise
timer abort, stale queued sends/session state, normal callbacks, destroyed
receiver reentrancy, duplicate/resume visibility and concurrent ticket identity.
Three original lifecycle tests still execute the actual event body. Four Pico
checks verify real Qt/free-function compilation, early hook order, later
connection and original target ownership. Shared v002 also adds its original
startup compilation regression, bringing that HTTP check file to three methods.
Full platform compilation, live transport behavior and device timing remain open.

## Direct-domain DNS generation binding

sh005-scoped-hostname/v001 source a0a067f05fcf35acdb9777c657fa2b7649bd96ae,
manifest f61a07a814241f4b575e73aeecccb7d647a2098288c14c0d757dd4acbf5546af.
The actual Shared DomainHandler owns ScopedHostnameLookup. Pico's existing
networking target/NodeList/getDomainHandler path consumes it directly; there is
no new platform hook or copied resolver. A new start invalidates the prior
generation before Qt abortHostLookup, and hardReset cancels before emitting
resetting or changing the domain. Only a current, once-consumed callback reaches
the original socket setter. Receiver/owner destruction, reused resolver IDs and
queued/duplicate stale callbacks cannot revive an old generation.

Two original focused tests compile the original helper and DomainHandler launch
expression. Real Qt objects plus an OS-resolver-only deterministic substitute
exercise negative/reentrant cases; a separate real Qt asynchronous numeric
loopback resolution runs in an isolated network namespace. No external resolver
or domain connection is contacted. Pico's additional source test verifies the
original networking/NodeList owner path, not a full DomainHandler build.
Qt resolver abort is best effort, not proof of finite OS cancellation latency.
Foreground suspension, ICE SockAddr, UDP/check-in/STUN/reconnect, connection
deadline/recovery/trace and entity consent remain explicitly pending.

## Effective Qt/native visibility — required current startup migration

sh005-visibility-inputs/v001 source ac91ed99ffd518bf8a719a9620a00b26c1c78c65,
manifest 157d5ec36aae0d1579cef6a7c45aaf472474dd60e876e63cab90bee19096cb5a.
The exact released startup override now includes ApplicationLifecycle.h and
calls observeQtVisibility(QGuiApplication::applicationState() == Qt::ApplicationActive)
after BOTH AddressManager and NodeList creation (latest NodeList migration below).
This replaces the earlier direct HTTP setter;
the existing later activeChanged seed/connection remains. Original Shared
publication owns one process input combiner: Qt must be active, and an observed
native false is an additional veto. Both navigation Gate and real HTTP receive
the Gate's returned effective foreground, including its terminal Stopped state;
the later NodeList contract forwards that same effective value to transport guards.
No input source can erase the other's denial. Unobserved native input retains
Qt-only semantics, not evidence of native state.

PicoInterfaceActivity's existing onCreate/onResume/onPause/onDestroy now supplies
Activity foreground to PicoClientVisibility. Window focus, headset/XR state,
permission and audio eligibility are separate and are not fed into this bool.
Only the current Activity owner can publish; replacement attach starts denied.
The Java helper retains one latest unavailable observation, weakly references
the Activity and schedules at most one retry (50ms backoff capped at1000ms).
Missing JNI/full QCoreApplication is retried while an owner exists, with one
closed diagnostic per unavailable period. Final detach attempts deny and stops
ownerless retry. These timings are not a hard startup/application-stop bound;
before the first successful native delivery Shared still has Qt-only authority.

The native bridge is deliberately outside the common src glob and compiled
ONLY into the full interface target, never early picoOpenXR or a second Gate.
Monotonic process generations reject obsolete submissions; the Qt-thread queue
discards stale allows but retains already accepted deny barriers, so rapid
pause/resume cancels earlier HTTP tickets. Signed counter exhaustion permanently
denies. JNI true means queue admission/discard, not applied visibility or OS
stop. Early/latest retries, native/Qt disagreement, duplicates, old Activity
callbacks, cross-thread queueing, quick pause/resume, missing JNI/app and counter
exhaustion are exercised by the real Java helper/native transport and COMPLETE
original Shared publication with real Qt objects. Only Android main-loop/log,
dependency registry/HTTP forwarding and test control points are substitutes.

The host test explicitly destroys its synthetic QCoreApplication before JVM
teardown; its first fixture version did so too late and crashed during host
shutdown. Those failure logs were retained privately, not accepted as proof.
The corrected fixture passes. Full Qt5/Android link, device ordering, actual
Activity/application teardown races and physical cancellation remain pending.
Rendering/audio/DomainHandler/ICE/UDP/STUN and informed consent/recovery are not
completed by this navigation/HTTP visibility contract.

Activity replacement teardown and window-focus loss scope global WebView cleanup
and input cancellation to the current owner, matching microphone ownership.
Previously a superseded Activity could destroy its successor's static WebView
map or cancel its input. Regressions executing the ORIGINAL onDestroy/helper/
onWindowFocusChanged bodies and real instance policy fail before each guard and
pass afterward. Current-owner WebView/microphone failures still do not skip
OpenXR release or Qt super teardown. Android/WebView/driver effects are test
boundaries; actual Activity recreation and WebView renderer ownership still
require device validation.

Shared V8 diagnostic prerequisite sh005-v8-diagnostics/v001 and v002 is consumed
unchanged (sources ecae47c374da16654b6bde9229953e4f889afbed and
8e635be20068cbf7ea50b57764a3d0aedb47bd8e; manifests
5b83a57703be7a640873c4c82aeaed6f38517d9c05cbeaee2a35218cbd6afcb0 and
f7f318cdb1bd1c3b0d462c8526cf7edb0003cda64eea89056a0c6f38b03564f8).
Pico's existing ScriptEngines setup uses the original V8 engine and compiler;
no native hook or copied diagnostic/consent API is needed. Original diagnostic
functions, syntax compilation and result class execute against real host V8/Qt
with six isolated scenarios in1.972s. Test-only engine storage is substituted;
Node22.23.1 host tooling is not the locked candidate22.22.3 binary or build input.

Captured metadata avoids exception.stack/prepareStackTrace execution, absent
messages are handled, and terminal diagnostics do not resume execution. This is
NOT a privacy-redaction contract: captured messages/files/backtraces still need
their Shared sink privacy work. Nor does this implement consent or production
TerminateExecution: default-deny entity-script fetch/compile/evaluate, informed
UI, finite in-flight revoke, lifetime ownership and fresh-isolate regrant remain
active Shared source requests. Full engine/platform compilation remains pending.

Additional prerequisite sh005-v8-property-copy/v001 source
e489cc48b758028a790b55ba6a3f23e2637cf48e, manifest
04f19d1f079f1d88a149f7c8ba25886e5c83a0aeb72611bfeef1fb0d1f57144b,
is consumed unchanged. Original ScriptManager->evaluateInClosure now uses checked
enumeration/get/set and publishes the cached global snapshot only on complete
success. Existing inherited/accessor/setter semantics remain, including their JS
execution. Actual helper and complete snapshot caller pass seven isolated real
V8 cases in1.768s, including hostile getters/proxies/setters, termination and
failed snapshot/clean retry. Complete closure evaluation is NOT compiled by this
test. No Pico hook, consent API, hard deadline or native cancellation is added.

property-copy/v002 source14c249d75a6af4ccb71736174508a04fbf3ffc91,
manifest6fad1db5040375ac945f775bff66404541bd6b5a053903e75ece691756297508,
additionally replaces the original closure Script.require transfer with checked
source/destination Script/require objects and checked cache enumeration/copy.
Callable require objects still work. Missing/type-invalid/throwing/terminated
property reads discard the incomplete closure with a balanced counter. Original
real-V8 test now covers15 isolated cases; no native migration or new API. Actual
registration, sticky lifetime-safe revoke/consent and whole closure/engine/native
build proof remain outstanding. Host-only test boundaries remain as above.

WebView teardown now isolates frame-callback removal and final view focus clear
like the existing editor/touch/buffer/loading/destroy steps. All cleanup steps
catch RuntimeException and OutOfMemoryError, including fallback cleanup in
creation/render failures. An original-method regression injected each effect
failure across two views; it was RED at unguarded callback removal, then GREEN
for both exception classes after the fix. Inactive instances are removed before
cleanup; a failed step no longer skips remaining resources or the second view.
This demonstrates control-flow resilience with synthetic faults, not recovery
from arbitrary heap exhaustion or a guarantee that a failed OS cleanup completed.
Actual Android Activity callbacks run these global cleanup methods on the main
thread; no queued replacement-owner safety is inferred from this fault test.

sh005-v8-property-lock/v001 source2c60b810997cf103cfe075fe673c711860d10a4e,
manifestc9ff34c871dd5820ae0043338162521b9fa9031323fc90813c314e7f55c8a2eb,
is consumed unchanged beneath the same ScriptManager (actual Script/require and
remoteCallerID named-property accesses). Original ScriptValueV8Wrapper getter
now releases its Qt read lock even when V8 throws/terminates, omits property
names/object conversion from its failure diagnostic, and does not wrap a result
while terminating. The complete original method with real Qt/V8 passes five
isolated outcomes and verifies immediate write-lock acquisition afterward.
No native hook, reentrant-write safety, wrapper lifetime fix or bounded revoke
is inferred; full engine/platform and remaining Shared source requests persist.

property-lock/v002 source4c68d274ec7a7081d83b2848287f22a8dce6ddd0,
manifest644be4061b3ee7f7bd4a65be68f29a144f59197af1b2a542d8dbf7c35e2bab9b,
is consumed unchanged for the original V8 ScriptValue::data getter. The existing
__data script property is NOT protected storage. Nonobject input retains null,
ordinary missing/throwing lookup returns undefined without a debug assertion,
and terminated lookup returns an empty ScriptValue without wrapping V8 data.
Outer exception handling is retained. Both complete original getters pass ten
real V8/Qt cases with test-only value/engine ownership. No native hook, new lock,
lifetime/consent/revoke guarantee or private storage semantics is introduced.

sh005-v8-iterator/v001 sourceef2c3bafd1bff6e22f4e48b0c9877c8304574fd5,
manifest8121adb93bd9ad62c2b70e99f836343578c4a2a8a82b0ecb4f57c5eca87809ca,
is consumed unchanged for the original ScriptValueV8Wrapper iterator factory.
The complete original iterator class/six methods pass seven isolated real V8/Qt
cases: normal order/value delivery, empty/nonobject/pre-next access and throwing/
terminated ownKeys/getters, including actual persistent-handle destruction.
Failure leaves empty iterator or undefined value with the outer exception intact;
no dynamic key diagnostic is emitted. Engine/value ownership scaffolding is
test-only; general lifetime/native callbacks, remaining failure paths, consent,
finite revoke and full engine/platform proof are still outstanding. No Pico hook.

## Entity scripts: denial-only intermediate implementation

sh005-entity-default-deny/v001 sourcee4ac182036f4851ce9ba1b8299a39cc0d9295f0a,
manifest8dd4928d1132f2b6634a6a5fddbf83ec4330f9bb7b77b6ca3c32dc37bd7fdb31,
is consumed unchanged. Pico's actual ScriptEngines startup uses CLIENT_SCRIPT;
both persistent/nonpersistent EntityTreeRenderer managers use ENTITY_CLIENT_SCRIPT.
The original loader and content callback therefore deny before fetch/compile/
evaluate/preload on their owner thread, including late/queued callbacks. Immutable
constructor context is authoritative, not mutable script type, URL scheme,
redownload flag, environment or historical allowlist. No native allow hook exists.

IMPORTANT functional limitation: all client entity scripts, including local,
embedded, cached/file/network and avatar entity scripts, remain unavailable.
Existing detail observers receive ERROR_LOADING_SCRIPT with the fixed
ENTITY_SCRIPT_CONSENT_UNAVAILABLE code. This is a safe denial-only intermediate
version, NOT completed informed consent, usable grant flow, hot-reload revocation
or restored entity-script parity. Server/agent/test contexts retain their path.
The general trusted-script startup is not globally banned by this fence.

Original status/denial functions, enum and actual two entry prefixes pass real Qt
dispatch/lock tests1.498s, covering both client contexts, four source forms,
callback outcomes/thread queue, type/environment bypass and unaffected nonclient
contexts. Post-fence engine/network and signal receiver are explicit test
boundaries; this is not full ScriptManager/native or physical proof. Pico source
caller checks verify its real contexts and no duplicate native fence.

Functional consent UI, independently confirmed source/origin/epoch-bound grants,
lifetime-safe finite in-flight revoke/fresh-isolate regrant and restored local/
avatar functionality remain ACTIVE Shared source requests, not merely hardware
acceptance. Never add an allow toggle around this fence without that contract.

## NodeList foreground entry guards

sh005-nodelist-visibility/v001 sourcebe92baefc95271158c3e2e517166af5219e503d1,
manifest1f862b8a2af84465384b3c5f8ba8c001072ee1c6ae0762a957f33e3250892d82,
is consumed unchanged with the exact separately released Pico startup move:
one observeQtVisibility seed immediately after NodeList installation, following
AddressManager. Existing include, later activeChanged seed and real Activity/
JNI callback remain unchanged. Both installed receivers get the same effective
Qt/native/Gate value; early publication never constructs a dependency.

The original atomic C++-only setter prevents entry to domain check-in, ICE server
query, domain/inactive-node ping punch, hole-punch start and keep-alive pings while
suspended. Original timers/connection counters/packet bytes are unchanged.
Unmanaged assignment/server instances keep previous behavior; full-client type
changes cannot bypass the installed policy. Foreground permits old paths again
but does not itself invoke them. Stopped Gate still publishes false.

Original guard/state/full keepalive2 and complete Qt publication2 tests pass.
Pico actual Java/JNI + COMPLETE original Qt publication test now executes the
original NodeList atomic setter/state AND actual check-in entry guard, replacing
only the post-guard packet work with a counter. Every observed native/Qt pause,
resume, stale owner, queue boundary and Stopped outcome compares HTTP and actual
transport guard individually with the Gate (not an AND masking a missed denial).
Pico native2 PASS5.449s and source/startup7 PASS1.025s. No actual packets/device.

Entry checks are NOT barriers for sends already past them; native events take
effect only after GUI-thread publication. Existing timers may run again after
foreground. DomainHandler discovery/ICE SockAddr, LimitedNodeList STUN, transport
queues, in-flight/stale reply cancellation, generation-bound reconnect/retry/
deadlines/recovery UI and physical stop timing remain ACTIVE/deferred exactly as
appropriate. No full background network isolation or SH005 acceptance is claimed.

sh005-v8-invocation/v001 source0abecb2d2c14d5b97bcfdada7d221da6ddc14aee,
manifestcf3c0b186f11cbfe33ea8ae4754a1e7e2a9eabe53d9f98d55bdd3adbee82078f,
is consumed unchanged beneath original ScriptManager function/constructor calls.
Both COMPLETE list invocation methods validate fixed Qt argument capacity before
conversion/array writes in release builds, reject invalid receivers and empty/
terminated conversions, and release scoped Qt read locks before result/error
processing. Arrows remain callable but not constructors. Existing ordinary
exception behavior is retained; no diagnostic work is added during termination.
Sixteen real V8/Qt scenarios compile with QT_NO_DEBUG, checking limits, wrong
types, throws, termination, empty conversion and post-call write-lock acquisition.
Manager/context diagnostic and value ownership/cross-engine conversion boundaries
are test substitutes. Existing arguments-object overloads remain unimplemented.
No new native hook, safe whole-engine lifetime, sticky cancellation, informed
consent or finite stop deadline follows from this prerequisite.

sh005-v8-conversion/v001 source1049ffb5a5f0730b1d87569a58c6c924a7d0afd2,
manifestd3a4aeebe6a40cd7d32b418789740411a925429fb0ccac68d6a34b91338c8c19,
is consumed unchanged for original ScriptValue conversion/comparison callers.
Nine complete functions check thrown/terminated/empty V8 outcomes; integer
failure returns0, number failure NaN, strings/names empty, retaining outer
exceptions. Signed32 wrap uses V8 conversion; UTF8 strings/keys retain embedded
NUL via explicit lengths. Equals coerces exactly once, eliminating the previous
second-coercion exception/FromJust crash; missing/cross-isolate comparisons reject
before dereference. Existing enumerable property semantics remain unbounded.
43 isolated real V8/Qt QT_NO_DEBUG cases pass with only engine/value ownership
substituted. No historical crashing baseline rerun needed; General recorded it
read-only before release. Whole engine/Qt5/native, repr/native-proxy callback
lifetime, sticky cancellation, consent/grant/finite revoke remain outstanding.

## Qt-to-V8 signal dispatch

sh005-v8-signal/v001 source cda23f61216a596849d04ae5910db72e69e42008,
manifest eccaed74d40cc06e749ccb478e3d0a394ef4def62cb75cd8cb6729c0f425e81a,
is consumed unchanged. Existing Pico ScriptEngines use the original V8 engine;
its newQObject wrapper creates the original ScriptSignalV8Proxy, registered by
the original QMetaObject::connect path. No Pico override or native hook is added.
Captured-diagnostics v001 is the already-consumed exact source prerequisite.

The complete production qt_metacall checks the ten-argument limit before array
access/conversion, rejects missing storage/types and empty/terminated conversion,
skips empty/non-function callbacks without an unmatched context pop or script
diagnostic coercion, and retains global receiver fallback for missing/non-object
receivers. Observed termination stops this emission before later connections or
diagnostic/uncaught notification. Ordinary exceptions retain captured diagnostics
and later delivery; this does not make their contents privacy-safe automatically.

The original callback, moc-generated original base, real Qt signal emissions and
original lock run 13 isolated real V8/Qt QT_NO_DEBUG cases (PASS2.380s).
Value ownership, engine conversion, diagnostic receivers, connection registration
and signal names are test substitutes. Pico source checks pin the existing
engine/proxy/connection path; they do not execute full production registration.
Host Node22.23.1 remains a test tool, not candidate22.22.3 or a build input.

Whole-engine/Qt5/platform and optional performance-statistics compilation,
registration/disconnection, QObject/V8/native-callback lifetime and blocking
native calls remain pending. This prerequisite is not sticky cancellation,
informed consent/grant, a finite revoke backend or physical headset acceptance.

## Scoped ICE hostname discovery

sh005-ice-hostname/v001 source 5177f6c24d47f1cbcddc7fd0265c4eb687f06315,
manifest 5c10a279c23e42ae96904eb27126f086c95d324eee8ea28b63c957418961a814,
is consumed unchanged, using the exact already-consumed scoped-hostname v001
and RequestCancellation prerequisites. The actual AddressManager ICE request
connects through original NodeList to DomainHandler; its completion still
reaches the original foreground-entry-guarded ICE heartbeat handler. No Pico
native hook, duplicate resolver or common API is introduced.

DomainHandler owns a separate generation-scoped ICE lookup. hardReset cancels
both direct and ICE lookups before resetting signals/state. Stable SockAddr
value assignment replaces explicit QObject destruction/placement construction;
late/reentrant, reused-ID and duplicate resolver replies cannot update a newer
lookup. Numeric fast paths and original IPv4 asynchronous selection remain.
DNS error/empty/IPv6-only asynchronous results do not emit successful completion.
Abort remains best effort and both owners require their event-loop thread.

Complete original setter/completion and actual reset cancellation prefix pass
the released real Qt6/Network test (1 test, 1.748s); original direct DNS checks
also pass (2 tests, 3.181s). Resolver, SockAddr value storage, timing/signal
receivers and the remaining reset body are test boundaries. Pico source checks
pin the real routing; they are not full DomainHandler or transport execution.

Foreground discovery suspend/restart, other SockAddr/STUN/ICE-response and
transport queues, in-flight/stale replies, generation-bound reconnect/retry/
deadlines/recovery UI and closed DomainHandler diagnostics remain ACTIVE.
Whole DomainHandler/Qt5/platform compilation, physical headset and original
artifact gates are pending. This resolves reset/domain-switch ICE DNS lifetime,
not full background network isolation, consent or finite revocation.

## Direct/ICE discovery foreground binding

sh005-discovery-visibility/v001 source 6026087a7942c224ac0086ece436cb61f5302ac1,
manifest 83c72c242b095114af7db65739faa3b793fe668d0850483f50a62cad63575b8b,
is consumed unchanged after NodeList visibility, scoped ICE and DomainHandler
diagnostics v001. The existing effective Qt/native publisher now reaches original
NodeList::setClientTransportVisibility and DomainHandler::setClientDiscoveryVisibility.
No additional Pico lifecycle authority or native hook is introduced.

An atomic discovery snapshot invalidates older direct/ICE replies at publication;
resolver cancellation runs in the DomainHandler event-loop thread. Exact snapshot
matching rejects stale queued pause/resume work, including after hardReset.
Background target changes retain current metadata without launching DNS. On
foreground, an unconnected unresolved current target is resolved again; numeric
ICE completion is also visibility-guarded. Duplicate visibility does not restart
work. Unmanaged assignment/server instances retain their original active default.
RequestTicket::matchesSnapshot accepts suspended generations for cleanup only;
network work still requires current(). It is not an authorization/grant API.

Original complete visibility method, both launch helpers, ICE setter/completion
and reset prefix pass the real Qt release test (1, 1.849s); affected direct DNS
(2, 3.332s), NodeList (2, 1.090s), HTTP (3, 3.880s), visibility publication
(2, 1.816s) and raw DomainHandler diagnostics (1, 1.442s) also pass.
Pico actual Java/JNI/full Shared publication/NodeList setter now executes the
complete original DomainHandler visibility method (2 tests, 5.876s). Assertions
check HTTP, NodeList entry and discovery state separately and compare independent
HTTP/discovery tickets through pause/rapid resume. Resolver launch/completion
effects and socket storage are substitutes in this Pico transport fixture;
the original Shared test separately executes real launch-helper bodies with
resolver and socket boundaries. Pico caller source checks pass (3, 0.007s).

This resolves the previously requested direct/ICE DNS foreground binding, not
callbacks already past their guard, hard OS resolver deadlines, other SockAddr/
STUN/ICE replies, UDP queues, settings/auth work or complete generation-bound
connect/reconnect/deadline/recovery. NodeList guards remain entry-only; informed
consent/finite revoke, whole Qt5/platform compilation, physical timing and all
original artifact/headset acceptance remain pending.

## HTTP session owner type correction v003

sh005-http-cancellation/v003 source b71f7f9f25aa570405b41f2d36775727616078c6,
manifest 06fdef87d1767f9286ee9b6c74a01ab3c9a57de2fc383ab6efa6b738a8af18d0,
is consumed unchanged with all four files. Existing HTTP v001/v002 and current
visibility startup are prerequisites; no QML/privacy prerequisite follows merely
from commit ancestry. Apple has a separate test-only migration, not imported here.

Actual AccountManager.h already owns a QUuid session ID. The older focused test
substituted QByteArray and therefore missed a real Qt6 compile failure in the
complete sendRequest body. The production header-to-session assignment now uses
explicit QUuid::fromString(QString::fromLatin1(...)); the production field type
does not change. Prior host evidence did not establish this real-field boundary
or whole AccountManager compilation and must not be treated as doing so.

Updated tests compile the exact original field declaration plus complete original
request/callback/AddressManager methods. Current valid headers update the UUID;
stale generations and destroyed receivers retain the prior UUID. Real Qt abort/
timers/concurrency and current startup visibility remain covered. Network request
creation/account/callback receivers are test boundaries, not OS transport.
Pico still uses the original AccountManager with its protected-store startup
registration; no local copy, conversion shim or new native hook is introduced.

Malformed current headers still become Qt's null UUID, not a new protocol or
authentication validation policy. Qt5/whole networking/native transport,
retry/recovery/in-flight deadlines/other queues, full consent and original SH005
acceptance remain pending. No candidate artifact is relabeled with this source.

## Original engine string factories v001

sh005-v8-string-factory/v001 source 7719a29a64d19f8e08f57aaebb4bd11dbbf1531f,
manifest 4590b0d89a1d670d545a1f4aae55ccdd2d79e62071e791ba5a2cf969c8dddb2f,
is consumed unchanged; all four release files match. Existing engine wrappers
are the only code prerequisite, with no new native hook or HTTP dependency.
Pico Setup still creates ScriptEngines; ScriptManager constructs the original
ScriptEngineV8 through newScriptEngine. Existing virtual string overloads and
the require error caller reach this implementation, with no Pico engine copy.

QString now uses explicit UTF16 code-unit lengths, including embedded NUL and
lone surrogates. Bounded QLatin1String uses explicit one-byte Latin1 length;
high bytes and nonterminated views no longer receive UTF8/C-string treatment.
The const char* overload retains NUL-terminated UTF8 semantics. Checked V8
MaybeLocal failures, excessive lengths and null C-string pointers return invalid
ScriptValue; empty QString/Latin1 still create empty strings.

The three complete original methods pass fourteen real Qt/V8 QT_NO_DEBUG cases
(one test, 1.462s); engine/context/value ownership storage remains substituted.
The Pico source check pins actual factory/caller wiring, not whole engine
execution. Host Node22.23.1 tools are not candidate Node22.22.3 or build inputs.
No baseline crash was rerun. Native pointer validity, isolate/engine lifetime,
allocation failure/process OOM, Qt5/full native compilation, sticky cancellation,
informed consent/grant/finite revoke and original SH005 acceptance remain pending.

## Domain credential reply generation v001

sh005-domain-auth-generation/v001 source d802abfa72d4db39e648553f467523c676e9c6e0,
manifest 29ede4c5d3c2a299b23bbced0da1f4f9a0e66b7cc6b18482e915993949a37158,
is imported unchanged with all five files matching the release. In addition to
HTTP v001/v002 and original SafeDiagnostics, this code requires snapshot() from
sh005-discovery-visibility/v001. Pico already has its exact RequestCancellation.h
hash 4e348bbe82e4e5c3be0705e0bb73f80bf880fd0b4e3023ea71465142df8acdce.
The omitted release prerequisite is reported to General; no competing helper.

Original Pico Setup creates DomainAccountManager and connects its authRequired
to the existing domain login dialog. LoginDialog::loginDomain dispatches to its
requestAccessToken; DomainHandler sets domain/auth/client context, and NodeList
newTokens triggers original check-in. No Pico account-manager copy or native API.

Domain/auth/client changes, a new request and destruction invalidate the existing
opaque request scope before abort; only one owned/current reply installs tokens
or emits success. Duplicate/no-sender/stale replies are rejected. The original
500ms login dialog captures the same snapshot. Successful token/cache behavior
is retained and all five DomainAccountManager diagnostic expressions are closed.

All original methods and real Q_OBJECT header/moc, Qt post/reply/JSON/timers pass
(1 test, 7.272s); dependency/NodeList and network transport are substituted.
Affected original HTTP tests pass (3, 3.835s). Qt SFINAE warnings were retained.
Source caller pins are not full UI/network execution; no historical crash rerun.

The preceding Shared LoginDialog::loginDomain still logs username; that concrete
sink is separately requested from General, not sanitized by this manager delta.
Global foreground cancellation, finite auth deadlines/recovery, cross-thread
ownership, TLS/redirect/origin policy, strict response type/expiry/refresh and
cached-domain authorization remain pending. No full SH005/PX15/PX16 or physical
domain-login/installed-artifact acceptance is claimed.

## Domain credential event-loop deadline v002

sh005-domain-auth-generation/v002 source 3dbac48fe069daa8584eabf336cb1056a7baacd3,
manifest 0aa04d9b2d911333733fc9173b8ada6019a2179a53b833e247d7f9dcb117a0f9,
is imported unchanged; all four files match. Existing v001 plus its actual
discovery snapshot/redaction prerequisites remain required. No new native API.

Each pending reply owns a real single-shot 15000ms Qt timer. A current timeout
invalidates ownership before abort and emits existing loginFailed once; normal
completion stops the timer. The QObject receiver context protects destroyed
managers. This adds no automatic retry. The original all-method/header/moc test
passes all v001 scenarios plus the ACTUAL production 15s wait (1, 22.162s),
checking synchronous abort-success cannot install tokens and reply deletion.
No shortened timer or synthetic deadline is substituted; Qt/OS scheduling is
not a hard stop bound during a blocked or suspended event loop.

Important Pico source gap: LoginDialog's constructor currently forwards both
account/domain loginFailed/loginComplete only under !Q_OS_ANDROID or the Phone
define. Pico is excluded although its domain route still calls this dialog and
LoggingInBody expects onHandleLoginFailed/onHandleLoginCompleted. The concrete
Shared receiver fix is requested from General, preserving Phone/Pico routes.
The manager signal test therefore does NOT establish Pico UI error/success
delivery or usable recovery. This is active source work, not just device proof.

The snapshot prerequisite correction and predecessor username log also remain
requested. Global foreground, thread affinity/hard OS deadlines, TLS/origin/
redirect/token expiry/refresh/cache policy, native Qt5/provider and all original
per-node acceptance remain pending. No candidate artifact is relabeled.

Subsequent source clarification: General's mandatory additive domain-auth
PREREQUISITE_CORRECTION_20260906T0624Z.md (SHA256
27d5295154f303109cf2f7dac0d5590befe89a17a26d339460056a098cd0e4ed) confirms
the exact discovery helper already used by Pico. That prerequisite request is
resolved without modifying sealed releases or relabeling test results.
px16-login-dialog-diagnostics/v001 now closes the predecessor username sinks
(see SECURITY_AND_PRIVACY.md). The Pico completion/failure receiver gap and
remaining auth/UI recovery requirements are still ACTIVE.

## Original domain login terminal receiver v001

sh005-domain-login-receiver/v001 source 37bd8a48fceab461fa61c9cf27f693b7677678db,
manifest 0a5988f9c650cd22ac6792e1fc61253c6b17afcb1b9ad3ad45320dcc3a4b9374,
is consumed unchanged for Main/Pico with all five files matching. Original
LoggingInBody.qml hash 6d0e619f2f850b9ca713692c981704e87c3ae988568a852c0066e436d29b1820
and PhoneLoginState.h hash 3da63a04c1278f75b5aa0cf92fc110e84a64edbf906ee91a8ac6512515931010
also match the pinned source. The separate Apple variant is not imported.

Only the two DomainAccountManager terminal connections move outside the existing
Android account/focus guard. Exactly one success/failure forwarding now reaches
Pico's original LoginDialog QML handlers. AccountManager's native Android path,
Phone pending-state cleanup, focus, dismissal and HMD/Tablet showWithSelection
remain unchanged. This resolves the concrete missing Pico receiver request;
it does not replace Setup or add a platform-specific signal/schema.

Explicit OVERTE_LOGIN_VARIANT=main compiles the complete original constructor
with real QObject/moc and original PhoneLoginState for Pico/Phone/desktop/iOS.
Real QQmlEngine/Connections executes complete original success/failure handlers
and loadingSuccess (1 test, 9.918s). Single forwarding, failure spinner/glyph
state, original loader payload, success callback/timer-start request, existing
account/focus/dismissal and receiver destruction pass. Manager/visual objects,
timer-start effects and loader are explicit boundaries, not whole rendered UI.
Pico actual caller/unguarded unique domain connection source1 passes (0.003s).

The real manager's 15s deadline was separately executed in v002 against the
mandatory discovery snapshot helper; the receiver fixture emits its original
signals but does not rerun that timer or network provider. These are distinct
proof scopes, not one end-to-end native login test. All failure causes still
become the original bad-credentials message. Typed timeout/recovery, domain
selection preservation on reload and cross-dialog request identity remain
ACTIVE Shared source work, alongside foreground/auth policy and original
native Qt5/provider/HMD/artifact/consent/physical gates.

## Domain credential form, redirects and response bounds v003

sh005-domain-auth-generation/v003 source 8883d2009a096abff0aba770dcdedb8569d82d2c,
manifest ad441be7a517be0b272ef39012ca6d2b9977204106a272f24e6209f20d007017,
is consumed unchanged with all four files matching. Existing v001/v002, exact
discovery snapshot helper and redaction prerequisites are now explicitly named
in the release itself. No receiver dependency, new header or native API.

Original requestAccessToken percent-encodes client_id as well as username and
password, preventing added form parameters. ManualRedirectPolicy disables
automatic credential POST replay; 3xx is rejected. Reply buffering is configured
to 1 MiB plus one sentinel byte; oversized readyRead invalidates ownership before
abort, and the final read/JSON input has the same bound. Exactly 1 MiB remains
accepted when valid. This is not a total Qt/TLS/decompression/JSON memory budget.

Only error-free 2xx valid JSON objects with a nonblank string access_token and
an absent or string refresh_token can install credentials and signal success.
Empty optional refresh token remains allowed. A network error with a 200/token
body is still failure. Rejection uses existing loginFailed with no payload log.
The unchanged Pico domain-manager/terminal-receiver route remains in use.

The complete original methods/header/moc test exercises actual form bytes,
redirect/read-buffer settings, thirteen invalid payloads, 3xx/network-error200,
streaming/final oversize, duplicates, inclusive-size success and the real15s
deadline. Network/dependency effects remain test boundaries. This is not an
end-to-end TLS or rendered UI test, and no baseline crash is rerun.

Initial auth origin/HTTPS approval, token syntax/expiry/refresh/cache semantics,
global foreground and typed timeout/recovery/cross-dialog identity remain
ACTIVE. All failures still reach the existing undifferentiated QML message;
the receiver fix does not supply typed recovery. Whole native Qt5/provider,
consent and original per-node artifact/headset acceptance remain pending.

## Published General auth release drain (2026-09-06)

Wave31 consumes fourteen immutable Main releases, from login-pending-ownership/v001
through account-auth-context/v001; exact versions, prerequisites, General/import
SHAs and manifests are recorded in the sealed handoff. All exported bytes matched
immediately after each ordered import. Shared commits are DO_NOT_REPLAY.
Domain-outcome/v002 is the mandatory selected-Phone companion, not Pico UI proof.

This supersedes the preceding pending statements ONLY for these source behaviors:
request-bound queued domain success/cancel/timeout/failure, generic typed recovery,
domain session-cache invalidation on auth/client/replacement login, and effective
Qt/native visibility delivered to the real DomainAccountManager. Existing Pico
startup installs that manager before visibility seeding; no second observer or
Pico manager implementation was introduced. Account request forms, redirects,
bounded validated completion, real15s deadlines and logout/changed-URL context
fencing use the original installed Shared AccountManager and protected-store hook.
Raw Login QML and AccountManager diagnostic sites use closed messages.

Pico tests now pin request identity/context/queued outcome delivery before the
Android account guard. Actual Pico Java/JNI and the original Shared publisher,
DomainHandler discovery, NodeList entry fence and DomainAccountManager visibility/
invalidation bodies execute together with real host Qt. Each receiver and old
ticket is compared independently; no combined result hides a missed denial.
Pending auth transport/outcome effects remain boundaries in this Pico fixture;
the complete Shared manager/moc/reply test verifies those separately.

Focused final family checks: eleven Shared runners (twelve test methods) PASS,
including actual15s domain and Account deadlines; two Pico source assertions and
two Java/JNI visibility tests PASS. Initial Pico fixture failures exposed obsolete
raw-signal assertions and a missing new receiver, corrected without editing Shared.
No historical crashing baseline, full suite, native build, device or remote write.

Remaining: initial origin/HTTPS/TLS and token semantics, same-context Account
request ordering/foreground/UI cancellation, reentrant/thread/OS-stop guarantees,
complete loader/selection/focus/provider/native Qt5 integration, informed consent
and entity grant/revoke, authentic graph/artifact receipts and original PI-002
through PI-007 headset acceptance. This is not whole parity or node acceptance.
The user's latest instruction ends this drain after one new-release check and
requests goal pause; it supersedes the previous automatic monitoring rule.
