# Optional World GPU frame timing proposal

Prepared source only. This proposal does not enable diagnostics in `main.ts`,
change pixel ratio, render resolution, scene contents, lighting, materials,
quality or presentation. Actual browser/GPU capability and overhead checks are
pending. Fake-query CPU tests do not establish GPU support or fluidity.

The World patch applies to the exact source hash in
`WORLD_GPU_TIMING_BASE.json`; apply the narrow patch instead of copying this
snapshot's World file. The existing observer manifest remains unchanged.

`WorldOptions.gpuTiming: true` is an explicit constructor-only opt-in. Default
Worlds allocate no timer queries and expose `gpuTiming: { enabled: false }`.
Opt-in captures one draw every eight actual normal presentation frames. An
owned identity token, not a GL handle, brackets that renderer invocation. Its
begin/end/poll work stays outside the existing `graphicsSubmit` CPU interval.
The CPU paired sample adds one monotonic timestamp on sampled successful draws;
the existing CPU phase remains independently measured. A rendering exception
still propagates, and `finally` ends only the owned diagnostic sample.

There are at most eight owned query handles. The deadline is five seconds,
shortened to 2,147 ms for a 32-bit counter to avoid wrapping. Query results are
read only after asynchronous availability and a non-disjoint state. The
observer neither ends/deletes a foreign query nor consumes its disjoint flag.
Polling is bounded by eight handles and occurs on existing animation tasks,
including when Tablet pauses presentation. No timers, readback, `finish`,
blocking wait, new animation task, global GL wrapper or foreign profiler hook
is added. Hidden-page animation suspension cannot grow the pool; on resume it
expires old work, and teardown releases ownership before renderer disposal.
Context loss remains explicit until the World is replaced. Unsupported
extensions, invalid counters and absent WebGL2 APIs return null GPU means;
WebGL1's older timer extension is never substituted.

Manual visitor `captureScene` remains an independent draw without sampled
normal-frame accounting. Shared capture or other profiler activity during an
already-owned synchronous frame is not introduced by this patch.

The aggregate snapshot contains no device strings, world identifiers, URLs,
GL handles or pixel contents. CPU submitted samples and completed valid GPU
samples are separate populations. `comparablePopulation` is true only after
all paired samples completed without pending, disjoint, failure, loss or
deadline exclusions. No subtraction synthesizes a frame-stage breakdown.
TIME_ELAPSED around a complete renderer draw can include GPU idle gaps while
CPU commands arrive; it does not isolate fragment shading, driver CPU cost,
compositor latency, VSync or total presentation time. Timer instrumentation
may itself cost time, so a source-coherent diagnostic cohort and an uninstrumented
control remain necessary before attributing Firefox's fluidity deficit.

The preserved compressed-runtime evidence has Chrome's 1,280 x 800 buffer
against Firefox's 2,133 x 1,333 buffer at the same 1,280 x 800 CSS viewport:
Firefox renders 2.7766494 times as many pixels. CPU submission duration alone
does not prove this is the limiting stage. This proposal measures rather than
changes that platform difference.

Validation commands after applying the narrow patch and copying new modules:

```sh
node --import tsx --input-type=module -e 'await import("./src/gpu-time-observer.test.ts"); await import("./src/world-gpu-timing.test.ts"); await import("./src/world-gpu-timing-integration.test.ts");'
./node_modules/.bin/tsc --noEmit
```

Actual-method tests preserve default-off rendering and CPU records, opt-in
ordering, Tablet pause polling, renderer exception propagation, independent
visitor captures and release-before-renderer teardown. The observer and
adapter tests independently exercise async query availability, foreign
ownership, finite caps/deadlines, counter width, disjoint loss, context loss,
token identity, unsupported APIs and repeated cleanup.
