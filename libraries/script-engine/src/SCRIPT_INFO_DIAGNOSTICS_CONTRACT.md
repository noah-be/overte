# Script info and same-thread shutdown public diagnostics

v010 redacts the actual destructor's public qDebug event without formatting
script type or filename. Scope guard, seven resource resets, return-value reset,
deleted marker and fixed ENTITY_CLIENT printf are unchanged. The new focused
fixture compiles the complete actual destructor with real Qt logging and explicit
engine/resource seams; both script types reject filename canaries and preserve
ordered cleanup under the guard. Baseline fails the actual private-world log
assertion; corrected implementation passes. This is not full native destructor
or real resource lifetime proof, nor complete script privacy/consent acceptance.

v009 is an evidence-only extension: no production behavior changed. A real
QThread is held before its event loop starts; actual stop(true) on another thread
must immediately deny both late cache outcomes while _isFinished is still false.
After releasing the event loop, the original queued stop finishes exactly once.
The fixture restores QObject affinity before destruction and uses bounded process/
thread waits. A compiled mutation moving invalidation into target-thread work
must fail the precise queued-stop content assertion (not an unrelated failure).
This verifies this specific cross-thread admission ordering, not the surrounding
manager's general thread safety, full native/header or finite evaluation stop.

v008 deactivates the load RequestScope immediately in the actual stop method,
before any optional thread marshalling. Late success/error cache completions and
new load requests cannot change contents or emit load outcomes after stopping.
The fixture now executes complete production stop as well as loadURL/suffix
methods, using actual QObject/invokeMethod and real atomic RequestScope. Both
marshal=true (same-thread Qt delivery) and repeated direct stop preserve the
original exactly-once runningStateChanged behavior. BaselineRED2.098s proved
late stopped-source overwrite; no evaluation/event-loop termination changed.
Cross-thread manager state, physical cache abort, finite script revocation and
full native/header integration remain unproved. Scope invalidation is not a
claim that currently executing script code stops within a bounded time.

v007 rechecks load completion ownership after the public Qt diagnostic, since
a synchronous message handler can start a replacement load. Actual Qt handler
reentrancy baselineRED2.101s exposed old contents overriding the new request;
the post-log fence retains prior contents/signals and admits the replacement.
No diagnostic format, request API or native/thread/consent acceptance change.

v006 scopes actual loadURL requests with the existing RequestCancellation.h
RequestScope/RequestTicket implementation. A newer request (including an invalid
suffix) supersedes prior completions even for the same URL. A callback advances
the scope before delivery, consuming duplicate callbacks; completion ownership
is checked after reentrant error and failure receivers before further signals.
Existing running-script rejection, weak/strong lifetime, reload/retry behavior
and public privacy remain. Counter exhaustion rejects further loading.
The actual-method Qt fixture uses the real scope implementation and proves stale
same-URL success, duplicate completion, reentrant replacement during error and
invalid-suffix supersession. Baseline stale-source assertion RED1.798s.
Both production header member/include and existing networking link are checked;
full original ScriptManager header/native compilation remains unproved. Atomic
tickets do not make surrounding manager state cross-thread safe or abort cache
downloads. This is not full cancellation, consent/revoke or full-node acceptance.

v005 additionally protects the actual loadURL cache completion lifetime using
the manager's existing shared ownership model: cache storage holds a weak_ptr,
and a live callback locks one strong reference before accessing this. Expired
callbacks return without logging, writing contents or emitting signals. The
strong reference spans reentrant error/loaded delivery without keeping abandoned
managers alive until network completion. Actual loadScript creates shared-owned
managers; direct unmanaged valid-load callers are not supported by this contract.
The actual-method fixture reproduces owner destruction in an error receiver
before the fix, then asserts retained ownership during delivery and destruction
after return, plus ignored success/error callbacks after prior destruction.
Original load outcomes and closed public logs remain tested. Request ordering,
thread-affinity/cancellation, direct QObject deletion and native integration are
not proved. This does not implement informed consent or finite script revoke.

v004 closes the loadURL cache-completion public sink: URL, server status and
thread identity are not logged. Actual loadURL and suffix methods execute with
real Qt and explicit cache/expansion/signal boundaries. Running-script rejection,
invalid suffix, deferred cache callback, success/failure with both isURL values,
reload/no-retry arguments, original source contents and internal error/loaded
signals are asserted unchanged. No cache lifetime, network or native acceptance
is inferred; internal error messages still intentionally retain their payload.

v003 additionally closes all three public debugPrint sinks: no manager, source
debugging enabled, and ordinary managed print. Debug severity and the original
internal ScriptManager::print(message) delivery remain unchanged. The complete
production function executes under real Qt logging in eight routes including
native parent traversal, absent parent/source location, and empty arguments.
Engine/context/logger-interface and internal console are explicit fixture seams.
Original baseline fails the public event assertion; corrected Main passes.
This does not sanitize internal console data or the remaining direct runtime,
module-loader, exception and lifecycle diagnostic sites.

v002 adds the actual error, warning and printed-message wrappers. Their public
Qt sinks use the same bounded event while retaining critical/warning/debug
severity. The five-method fixture exercises each wrapper's normal console,
entity and server-fallback routes and asserts original internal arguments.
Baseline of the newly covered wrappers RED1.598s; no console output removed.

Two public Qt sinks now emit the existing bounded Redacted diagnostic event:
the same-thread waitTillDoneRunning warning and scriptInfoMessage's qCInfo.
The actual wrapper no longer formats script filename or message for public logs.
Its internal infoMessage/infoEntityMessage routes and original message, filename,
line, entity and server arguments are unchanged. Actual consumers include
Application's ScriptEngines connection and JSConsole::handleInfo.

The focused test compiles both complete production methods with real Qt logging
and explicit thread/engine/signal boundaries. It executes same-thread shutdown,
already-stopped worker shutdown, ordinary info messages, entity and server
fallback routing. Public canaries are rejected while original internal console
contents remain asserted. Baseline with actual wrapper was RED1.597s; corrected
Main PASS1.440s. The earlier diagnostic conflated public and console sinks and
is superseded by this more precise two-method test.

This does not prove privacy for the internal console, direct script logging
outside these wrappers, all telemetry, native execution or full-node acceptance. Disabled
timeout blocks remain disabled and unmodified. No stop/evaluation/consent/revoke
behavior changes; entity scripts remain fail-closed pending complete consent and
finite safe revocation. Native signal transport/lifetime remains a separate gate.

Consume the complete matching platform source delta on its pinned base and
transitive contract chain. Preserve Apple-specific ScriptManager behavior; do not
replace the entire file with the Main variant.
