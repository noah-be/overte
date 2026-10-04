# Read-only plan: release initial surface waiting from real support

The current animation loop stops input and gravity while an unloaded Model's oriented bounds overlap the capsule, for up to15seconds. These bounds indicate possible missing geometry; they do not prove the model supplies the floor. The inspected native Hub snapshot included both a huge compound model (approximately273×213×273 units) and a small bridge overlapping spawn. Early real browser records showed zero movement despite10loaded mesh colliders. This is consistent with a broad pending bound suppressing a useful loaded floor, but does not prove which collider supported those particular frames. No runtime change was made in this review.

First measure the proposed geometry-before-textures cohort independently. It should make genuine nearby triangles available sooner without changing the waiting rule. Only then test a narrow support predicate against the actual resulting BVHs and avatar coordinates. Publish support count/normal/gap aggregates, not public entity identifiers or asset URLs.

## Nonmutating triangle support predicate

Add a read-only query to `MeshCollision` using its existing world-space BVH. Use the capsule's bottom sphere center (`position.y - PLAYER_HALF_HEIGHT + PLAYER_RADIUS`). A narrow bounded AABB around that bottom sphere rejects distant BVHs before a shapecast. For candidate real triangles, compute their closest point to that sphere center. A contact qualifies only when its distance is no greater than the actual sphere radius plus a small explicit tolerance (proposed20mm), and the normalized vector from the contact point to the sphere center has Ygreater than the existing grounding threshold0.5. Reject ambiguous zero-distance contacts until the normal solver resolves them. This matches the current capsule contact geometry rather than using an entity box or a center-only vertical ray. It also handles real sloping surfaces and edge contacts that a center ray misses. Ceilings and side-only wall contacts do not qualify. The triangle plane must also be walkable (`abs(normal.y) > 0.5`), independently of winding: an individual wall triangle’s internal diagonal can otherwise produce an upward nearest-point vector even when its whole surface is vertical. The actual sphere radius is the configured `PLAYER_RADIUS` (currently0.28), not a separate approximation.

The query must not modify the player pose, velocity, grounded state, collider geometry or current collision-solver scratch state. Reuse separate bounded scratch vectors. No generated triangle, synthetic support plane or material opacity heuristic is involved. Support should use current transformed BVHs; stale/removed roots cannot qualify. Check bounded live colliders and stop at the first qualifying actual contact. After an initial episode is verified the implementation performs no further support scan until a new spawn resets it.

## Initial waiting lifecycle

Do not simply replace `pendingSurface` with `pendingSurface && !supportsCurrentCapsule` on every frame: that would pause an ordinary jump when its feet leave a loaded floor while a huge unrelated model remains pending. Preserve jump/fall semantics explicitly.

The smallest coherent first scope is the initial spawn/reposition safeguard. Track whether actual loaded support has been established since the last `setSpawn`/authoritative teleport. Before that, retain the existing bounded pending-surface wait. Once a genuine support contact is established, release this initial wait episode and let the existing movement/gravity/capsule solver operate normally. Reset the support episode on a new authoritative spawn, not on repeated domain state packets. This requires checking the old15-second timeout semantics carefully: the current timer is already spawn-scoped and does not restart when a visitor later moves into another pending model. Do not silently turn it into a recurring region/ledge pause.

A future protection for walking into an unloaded neighboring region is a separate design requiring predicted support, explicit airborne/jump state and a bounded episode policy. It should not be bundled into this measured initial-ground fix.

## Required evidence

Pure actual-BVH tests: normalized/rotated native floors, slopes, real edge support, no floor, support below/above the20mm limit, wall/ceiling-only geometry, stale/moved/revoked root and unchanged input pose. AABB-only overlap must never pass. Compare contacts to the existing actual capsule resolver, including its0.5normal threshold.

Both browser engines: delay an unrelated huge Model after a genuine floor loads; verify realWASD and groundedY while the unrelated model remains pending; jump rises and falls normally without a loading freeze; a new unsupported spawn still waits for actual geometry; teleport/root replacement revokes old support. Use real authored model triangles and delayed actual asset I/O, not a built-in replacement floor.

Actual Hub: record the exact bundle/runtime identities and aggregate support gap/normal at early movement. Observe the independent native position, retain actual cold geometry/texture loading timestamps, and run the unchanged short walk/rejoin assertions. Fluidness gates remain unchanged. No claim of improved loading or solved initial movement can be made before this actual test.


## Separate prototype, not yet integrated

The amended staged-geometry World (`6d962c98…`) remains the dependency. The support patch is separate from both the preceding preparation-cache/scheduler cohort and staged-geometry cohort; applying it early to an older World is unsupported. `MeshCollision.supports` has five dedicated capsule/lifecycle regressions, including the wall-diagonal false-positive which failed before the walkable-plane guard. The existing capsule resolver and frame timestep remain unchanged. Disposal is idempotent and revoked colliders cannot provide support or correction.

`InitialSurfaceWait` retains one initial-spawn episode. An exact20mm gap is supported, airborne/underside poses are not. Real support releases the guard; subsequent legitimate jumps or falls cannot restart it under an unrelated pending model. A new `setSpawn` resets it. The existing15-second bound is retained across temporary gaps in pending bounds, including a timestamp of zero and subsequent clock regression.

The future staged-geometry/support overlay passed typecheck and20CPU regressions: four actual World preparation-cache/reader/queue tests; five actual World FST→FBX staging/failure/nested-mapping tests; six actual geometry-transform/ownership tests; five support/episode tests. Exact-host browser/native validation remains pending. The authored renderer fixture `tests/initial-surface.browser.spec.ts` waits for a real staged FBX floor BVH while its PNG and an unrelated1000-unit model are delayed, then requires WASD, airborne jump, landing, and unsupported authoritative-spawn guard reset. It is prepared for both engines and has not been executed in this restricted agent.

The narrow prototype verifies actual mesh-triangle support only. A primitive-only floor does not establish this triangle latch; its existing collision physics is unchanged and the original bounded pending-model safeguard remains conservative. Broader primitive contact verification is a separate reviewed change if real evidence requires it.

Exact source and patch identities are recorded in `support-prototype-manifest.json`. No public-world change, shader quality change, fictitious floor, or fluidness threshold reduction accompanies this prototype.
