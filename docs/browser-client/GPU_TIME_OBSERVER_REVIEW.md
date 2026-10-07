# Optional bounded GPU timing observer

Integrated as an immutable opt-in World diagnostic; the normal entry point is
default off. Twenty-nine focused CPU contracts and two actual browser pixel/
query-lifetime cases passed. Short strict stock-Hub cohorts were actually run;
Firefox remains unsupported without changing privacy settings. See
[the preserved results](evidence/hub-gpu-timing-runtime-20261001.json).

Primary API source is the [Khronos WebGL extension specification](https://registry.khronos.org/webgl/extensions/EXT_disjoint_timer_query_webgl2/)
(revision 4, June 1, 2023). The helper uses only TIME_ELAPSED queries. It checks
the query counter capability, checks QUERY_RESULT_AVAILABLE in a later browser
task, and reads a result only when available and GPU_DISJOINT is false. Result
nanoseconds retain their full safe integer precision before conversion to ms.
Unavailable extensions/counters produce no invented timing sample.

At most eight owned queries are retained by default, with a configurable strict
maximum of sixteen. Polling expires pending or accidentally unended active
queries at five seconds by default, capped at ten seconds. A 32-bit timer gets
a shorter safe deadline below half its wrap span. There is no synchronous wait,
busy loop, gl.finish, forced GPU readback, or getError consumption. Disjoint,
context loss, invalid result and ownership loss reject timings and release only
the observer's handles. A foreign active timer is not ended or deleted, and
the global disjoint flag is not consumed while that timer is active.

The caller polls on subsequent normal animation tasks and disposes on shutdown.
If animation is suspended, polling deadlines apply when polling resumes; the
strict query-count cap still bounds resources, and disposal closes everything.
The observer owns no recurring timer, DOM element, shader or renderer resource.
A bounded warning is emitted once. Snapshot fields contain only counts and
durations; no query handles, URLs, visitor identifiers or device labels escape.

The read-only World integration surrounds the existing renderer draw, outside
the graphics-submit CPU measurement if that metric must stay comparable:

```ts
const measuring = observer.begin();
try { renderer.render(scene, camera); }
finally { if (measuring) observer.end(); }
// A later animation task, not a blocking result loop:
observer.poll();
```

The source does not change resolution, DPR, texture quality, lights, scene,
materials, culling, uniforms or shader state. GPU elapsed time and CPU submission
time answer different questions. An elapsed query around a whole renderer call
can include GPU idle gaps while the CPU feeds commands; a duration close to CPU
submit time does not by itself prove fragment saturation. A much shorter valid
GPU interval can support CPU submission attribution. Measurement overhead also needs a separate
comparison before enabling diagnostics for performance acceptance runs.
The prepared actual-browser fixture checks the unchanged drawing buffer/DPR
and red pixel, then either a completed valid query or truthful unsupported
state, plus owned-query disposal. Actual fixture and Hub evidence establish the bounded diagnostic behavior,
not native graphics parity, Firefox fluidity or an FPS improvement.
