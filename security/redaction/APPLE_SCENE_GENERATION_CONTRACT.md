# Apple queued scene-observation generation fence

The actual EntityRenderer::updateInScene captures the Shared entity observation
generation before queuing its render transaction. Its real asynchronous callback
passes that immutable value to recordIOSRuntimeSceneEntity(entity, generation).
Callbacks queued while unarmed or before a subsequent begin no longer populate
the new scene counter. Duplicate entities remain de-duplicated. Ordinary render
update work still executes: this is observation cancellation, not cancellation
of rendering or entity mutation. Non-iOS preprocessing retains its old lambda.

Version 002 also captures a weak renderer owner at enqueue and locks it before
the first callback dereference of `this`. Queued work does not keep the renderer
alive. If it is gone, the callback returns without accessing entity/render state;
otherwise the strong local owner covers the whole invocation. The real factory
already creates EntityRenderer through shared_ptr, as shared_from_this requires.
This does not repair unrelated raw callbacks or promise arbitrary renderer
thread safety. The focused test queues the original lambda, releases its real
std::shared_ptr owner, verifies weak expiry and flushes without state mutation.

Each beginIOSRuntimeEntityEvidence advances a mutex-protected uint64 generation.
Zero is invalid. Exhaustion permanently disarms observation rather than wrapping
to an old ticket. The one-argument scene recorder is replaced, not implicitly
mapped to the current generation. All production uses (one) migrate together.

Import the two production files and both test files together. Requires the
preserved Apple runtime header and px16-apple-config-boundary/v001. The test
compiles the COMPLETE original updateInScene with the COMPLETE Shared header
and host Qt. Only entity/render transaction dependencies are substituted; the
test controls delivery order of the original queued lambda. It covers unarmed,
superseded, current, duplicate, invalid-render-item and overflow cases, and
compiles/runs the unchanged non-iOS branch. Native render-thread execution and
full renderer compilation remain pending.

This is one prerequisite of the requested structured evidence migration, NOT
the completed producer/consumer contract or acceptance evidence. Tree, commit,
handoff and draw-entry paths are not yet generation-bound. Existing scene/drawn
counters are not expected-entity intersections; draw entry occurs before
doRender and proves neither GPU submission nor visible pixels. These numbers
must not be promoted to world/render PASS. Domain resets, source/artifact/run
identity binding, bounded correlation sets, private structured transport and
the five legacy evidence-source consumers remain outstanding. No diagnostic
marker is restored and no acceptance assertion is relaxed.
