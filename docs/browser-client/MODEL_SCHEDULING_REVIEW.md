# Model scheduling and first walkable geometry

This is a read-only architecture review. No queue, physics or rendering behavior has changed.

The real Chromium 154 run at 2026-10-01 05:14 UTC first sampled 74 entities at 3.61 seconds after connection, with 33 loaded models and 10 mesh colliders. At 7.88 seconds, the world had 517 entities, 65 loaded models and 231 queued models. The matching Firefox 156 run initially saw 74 entities, 26 loaded models and 10 colliders at 3.98 seconds, followed by 517 entities at 8.85 seconds. Both recorded zero displacement during the early walking attempt. These observations establish partial entity arrival and a first-walk latency problem; they do not identify one exclusive cause.

The cached native 511-entity scene contains 310 models and 83 collidable model bounds. Two bounds overlap the observed spawn capsule: a large compound model measuring approximately 273×213×273 metres and a bridge measuring approximately 6.69×0.79×2.92 metres. The current loading hold waits for all overlapping unloaded model bounds. It cannot distinguish actual support triangles from an enclosing model bound.

Each enqueued model currently schedules a drain microtask. The drain sorts the entire remaining queue before checking whether all six loading slots are busy. A source-based replay of that cached scene performs 310 sorts and 95,608 comparisons; coalescing the drain and checking capacity before sorting reduces the same dispatch to one sort and 1,981 comparisons. Local replay timings are recorded in the [portable review](evidence/model-scheduling-review.json); they are CPU replay observations, not measured browser improvements.

The lowest-risk first change is a coalesced drain flag plus a busy/empty/disposed guard before sorting. This retains the existing six-slot limit and ordering while avoiding repeated sorts that cannot dispatch anything. Queue metrics should separately record dispatch CPU time and first collision-ready time. Removed tasks should be pruned immediately; active entity work should receive its own reader abort signal without revoking another entity sharing preparation.

A later priority policy can evaluate each queued item's current world bounds once per dispatch, rather than allocate vectors repeatedly inside sort comparisons. Priority classes are unresolved bounds intersecting the current or short swept capsule, visible nearby models, then remaining models by distance. Reserve every sixth dispatch for the oldest pending item so ongoing movement and arriving near objects cannot starve distant content. This changes loading order, never the eventual geometry set. Camera/visitor movement updates priority at the next free slot; it does not repeatedly cancel active work. All queue metadata remains bounded by the protocol's existing entity limit.

For progressive loading, split geometry readiness from material completion. After the actual FBX bytes have been normalized, decoded and parsed, apply the existing entity registration/rotation/dimension normalization and create the collision BVH immediately. Textures, native alpha classification, FST material overrides and shader compilation continue under the same owned resource scope. Geometry collision does not require image pixels in the current implementation. A separate geometry-ready flag must also drive transform-only BVH updates while materials are pending; otherwise a moving native entity could keep stale triangles. Keep initial staging scoped to Model entities, while avatars retain their usable fallback until the actual rig is fully ready. This permits real support geometry to become useful before every image has arrived.

Visual progression must use the actual authored data. Keep texture-dependent or pending-override meshes hidden until their maps and native alpha mode are known; already complete untextured parts can become visible after their real shader program is ready. Never invent a floor, opaque leaf mask, demo material or replacement bounds. Keep `loadedModels` as complete visual readiness and expose a separate geometry-ready count. Changing pending materials must restore batching before replacement and rebuild it only after final material identity is known. Texture failures remain visible warnings; session/entity revocation disposes both attached geometry and unfinished dependencies exactly once.

Before changing the loading hold, prove support using the already-loaded real triangle collider (for example a bounded capsule probe just below the feet), rather than interpreting an enclosing box as a floor. The unresolved compound model still loads eventually. The existing maximum loading deadline remains a limit, not a new early-success condition.

Validation should cover:

- A large same-tick entity batch dispatches at most six tasks and schedules one drain; busy calls do no sorting.
- Later arrivals and camera turns reprioritize pending tasks, while the oldest task progresses within six dispatches.
- Removing or replacing an entity revokes only its work; whole-world abort clears every pending task and stage.
- An actual textured FBX with a deliberately delayed image produces identical BVH triangles before image completion; final geometry, materials, alpha, UVs and pixels match the current completed result.
- Actual ground becomes walkable while its image is delayed, without relying on fabricated bounds; an unrelated enclosing box cannot keep already-supported movement frozen.
- Native synchronization, errors, full completion and reconnect remain unchanged in the short real-domain journey.

Measure each change in a separate uncontended real Hub cohort: first entities, first visible geometry, first actual support, early movement, complete loading, dispatch cost and steady fluidness. The initial queue guard, priority policy and geometry/material staging should not be bundled into an untraceable performance claim.

The read-only replay is reproducible with a locally captured native snapshot:

```sh
cd browser-client
node --import tsx lab/audit-model-scheduling.mjs /path/to/entities.json
```

Its output contains only counts, timing observations and the snapshot hash. It never reports entity IDs, source URLs or profile paths.
