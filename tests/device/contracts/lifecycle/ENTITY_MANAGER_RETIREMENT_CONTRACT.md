# Entity manager retirement before blocking cleanup

Both persistent and non-persistent EntityTreeRenderer resets, and both shutdown
manager paths, now synchronously request ScriptManager::stop before scheduling
retirement. The retiring manager remains shared-owned while a QtConcurrent worker
waits for run completion, then asks the still-live script event loop to unload
entity bookkeeping, disconnects signals and removes the registry entry. Cleanup
therefore cannot prevent the stop request from reaching an executing VM.
Aborted VM entry guards suppress user unload execution during retirement.
This intentionally ends graceful user-script unload execution on these retiring
client managers; ordinary individual entity unload remains unchanged.

ScriptManager::removeFromScriptEngines now locks the weak registry once and only
removes when it remains available. Application shutdown can release that registry
before asynchronous retirement completes. An expired registry requires no removal.

The focused fixture compiles the complete actual retirement helper, actual reset
prefixes up to replacement-manager construction, the actual shutdown retirement
region, and actual registry-removal function. A held worker, BlockingQueued cleanup,
QtConcurrent worker, shared ownership, deleteLater and destruction-to-thread-quit
are real Qt. VM execution and registry storage are explicit seams. Seven scenarios
cover both reset paths, both shutdown paths, already-completed run, expired registry
and empty managers. The earlier renderer fails immediate-stop checks and its
shutdown blocks; the earlier registry-removal function fails for the expired case.
Retained real-V8 interruption and complete-run lifecycle fixtures pass separately.
They are not a combined full EntityTreeRenderer/ScriptManager/native runtime test.

An already-entered native callback can still prevent run completion and occupy
the background waiter. This change does not claim a finite native cleanup bound,
physical resource cancellation, full shutdown ordering, consent grants or original
SH-005/IO-009 acceptance. Client entity scripts remain default-denied until a
complete source/origin/epoch-bound informed-consent backend is integrated.
