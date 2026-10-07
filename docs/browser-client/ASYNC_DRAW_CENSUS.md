# Task-sliced passive draw census

This implementation adds an explicit one-shot `drawCensusAsync()` diagnostic. It changes
neither rendering nor instance admission. The existing synchronous census stays
unchanged. No census runs from RAF or automatically during world entry.

The earlier real Hub census stopped at its 75 ms synchronous deadline after
34 owners, 50 meshes and 130 parts. Its censored grouping was zero; that is not
evidence of an instancing opportunity. This implementation addresses the diagnostic's
single-task limit with a deliberately separate async CPU budget, rather than claiming a loading or rendering improvement.

## Ownership and resource bounds

Each World permits one scan. A newer explicit request aborts the previous scan,
awaits its release before capturing graphs, and supersedes other waiting requests. The adapter captures one connected-session
source authority and requires model loading, queueing and shader preparation to
be idle before capturing graphs. It captures bounded private root/entity/signature
references and Scene transform values. Between task turns and before returning,
it verifies the authority, root collection, loaded/ready/failed state, source
signatures and candidate entity identities. Native changes to a previously
rejected dynamic/scripted/parented/animated/material-child Model may remain
rejected; a change into a potentially static owner refuses complete grouping.
Unchanged collection membership and root identities remain mandatory.

The scan uses an owned MessageChannel task continuation. It checkpoints between
owners/nodes, every 4 KiB of geometry hashing/comparison/verification, and during
terminal grouping/descriptor verification. The default slice target is 4 ms;
this is not a hard preemption guarantee for native reflection or a large single
object operation, nor a guarantee that MessageChannel runs behind every render.
Total async scan CPU is capped at 1,500 ms, wall time at 5 seconds, and task slices at
1,024. Configurable maxima are 8 ms per target slice, 2,000 ms total CPU and
10 seconds wall time. The report distinguishes active slice CPU, largest actual
slice, task count and elapsed wall time. Initial bounded World snapshot work and
caller result serialization are outside the scan CPU aggregate.

The synchronous API retains its exact 75 ms aggregate CPU ceiling. The async
CPU budget is a distinct, explicit diagnostic option, not a change to renderer
quality or performance acceptance gates. The original resource ceilings remain: 1,024 owners, 16,384 nodes, 8,192 parts,
64 MiB of total geometry-byte reads, and 2 MiB of charged diagnostic metadata.
The adapter additionally bounds captured native entities at 16,384, charges its
reference bookkeeping to the same metadata ceiling, and refuses excess sources
before iterating either map. At most 4,096 private grouping buckets are built.
Unique geometry bytes are copied into private request snapshots; terminal
verification and byte equivalence checks also consume the original read budget.
Consequently even a time-sliced request can stop before full coverage. It reports
partial counts and zero terminal grouping after any capacity, revision, abort or
deadline censorship. A late second grouping failure also zeros the first group.

Actual source/material/sampler/known-hook values are audited as before. No URL,
source name, entity/avatar ID, byte digest, private key or grouping key is returned.
The result exposes only bounded counts and fixed refusal reasons. Excluded owner
pose/matrix values are not candidate tokens: their counts are per-turn observations,
not an atomic snapshot of a moving scene. Shared resource structures still undergo
the existing bounded checks. Candidate transforms/materials and geometry bytes
are checked for inter-turn changes without invoking model getters.

The World adapter's source-owned revision is a diagnostic consistency boundary.
The implementation is not a JavaScript sandbox against arbitrary Proxies, nor an
atomic freeze against unrelated foreign code changing previously verified bytes
after a checkpoint. It is not permission to instance independently loaded models.
Picking, collision ownership, update restoration, frustum/light/shadow equivalence
and native edit authority remain unresolved admission requirements.

Completion, abortion and wall timeout clear private descriptor/array/byte maps,
close both owned ports, remove listeners/timers, and release the World's request
slot. No geometry, material, texture or original owner is disposed or changed.
Disabling the World closes the pending continuation ports synchronously; the
awaited finalizer then releases its private maps and request slot. A fresh
connected revision can start another scan without retaining the former request.

## Verification

The frozen candidate passes 118 targeted CPU cases with zero skips: 62 new async
scanner/actual BrowserWorld cases plus the retained synchronous census and task
ownership contracts. Whole-project `tsc --noEmit` passes.

The new cases include complete 293-owner scenes with shared and independently
allocated equal geometry/materials, exact synchronous grouping agreement,
inter-turn source/matrix/material/sampler/attribute/getter changes, World authority
and collection revocation, rejected dynamic pose updates, rejected-to-static
transitions, unchanged aggregate caps, late grouping censorship, genuinely
undelivered continuation deadlines and real MessageChannel port closure. A child
Node process with `--expose-gc` proves that completed requests do not retain the
original root, geometry, material or raw array buffer. The CPU test clocks are
controlled test inputs, not browser performance measurements.

The integrated checkpoint additionally passes the genuine undelivered-task
World-disable/reconnect regression, all 1,233 registered components without skips,
and the production build. Immediate port shutdown and awaited reference release
are distinct assertions; neither claims synchronous snapshot-byte release.

Run from the browser package:

```sh
node_modules/.bin/tsx --test tests/world-draw-census-async.test.ts tests/world-draw-census-async-owner.test.ts tests/world-draw-census.test.ts tests/world-draw-census-owner.test.ts src/worker-task-yield.test.ts
node_modules/.bin/tsc --noEmit
```

A fresh source-attested actual Hub run must await
`window.__overte.drawCensusAsync()` once after model jobs settle, save the bounded
result, and retain partial/refusal status. That browser experiment has not run
for this candidate. No full-Hub coverage, instance eligibility, speed gain or
Firefox fluidity result is claimed.
