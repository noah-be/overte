# One ScriptManager run lifecycle

`run` atomically admits one lifecycle per manager and retains a shared owner
through completion and engine-scope release. Repeated/reentrant calls return
without entering the engine again. `runInThread` also refuses a manager whose
run already began, so a completed direct run cannot create an unused worker.

After acquiring its engine scope, `run` installs the existing terminal work in
the project's production Finally guard. Normal exit and cancelled/refused start
both stop pending work/timers, release final entity packets, emit finished and
doneRunning, disconnect signal proxies, process pending events and finally set
the atomic done flag. scriptEnding is emitted only if initialization occurred.
The run caller's original thread-local file-access state is restored. Stop/global
admission is rechecked before initialization, after initialization and after the
running-state signal, before evaluating source. This does not interrupt a native
initializer that was already entered.

Manager destruction requests thread-safe QThread::quit directly. A queued quit
would target the QThread object's creator thread, which may be blocked waiting
for worker termination. disconnectNonEssentialSignals preserves that essential
wiring for a threaded manager even when isRunning is false: a worker can be
waiting to start or still running its event loop after script completion.

The fixture compiles the complete original run, runInThread, stop, isStopped,
waitTillDoneRunning and disconnectNonEssentialSignals methods, plus real Qt moc,
the original Finally class and actual LocalFileAccessGate implementation. Cases
cover normal completion, pre-stop, globally stopped collection, stop in init,
stop in the running-state observer, reentrant/repeated run, dropping the last
external shared owner in finished, a held QThread before marshalled stop, and
the real runInThread launcher/deferred-manager-deletion/worker-object cleanup.
Another case disconnects nonessential signals while that launcher is held before
run. Exact terminal counts, no forbidden initialization/evaluation, owner life,
thread-local restoration and no second worker allocation are asserted.

The VM evaluator, engine scope/proxy cleanup, static initialization and resource
implementations are explicit seams. Real V8 execution/termination is proved in
separate fixtures, not by treating this complete manager-method test as a full
native runtime. Original disabled unsafe thread-termination code stays disabled.
Scope-lock wait, already-entered native calls, full-header/native/JITless and
complete resource teardown/finite consent revocation remain unaccepted.

Read-only baseline cases fail on the previous run lifecycle. Controlled scratch
mutations restore queued quit or running-only essential reconnection; each fails
the real worker wait case. No production mutation switch or weakened assertion
is introduced by those optional fixture controls.
