# Genuine model geometry before texture completion

This runtime loading cohort follows prepared FBX caching/model scheduling. No change to the pending-surface hold policy is bundled with it. Actual short public-Hub measurements prove earlier movement while textures load, but do not establish faster full-world texture completion.

A `ModelGeometryStage` borrows the actual parsed Three model while the loader owns its pending image and FST material work. It uses the same bounding-box centering, entity dimensions and registration offset as the completed Model entity. The normalized model lives in a detached collision container outside the scene. Only the real world-space triangles are published as a `MeshCollision`; there is no temporary box, synthetic floor or visible substitute material. The container copies the current entity root's world matrix, so native pose updates rebuild the pending collider before textures finish. On Three 0.186.1 manual matrix changes also explicitly set `matrixWorldNeedsUpdate`.

The callback is supplied only by queued Model entities. It is forwarded through FST dependencies and invoked immediately after real FBX parsing, before its image completion wait. FST avatar metadata remains unchanged, and actual avatar loading does not opt into this callback. Formats whose loader delivers geometry only after their dependency completion keep that behavior. Material maps and texture overrides preserve the same hierarchy and triangles.

The entity root stays hidden. `modelGeometryReady` tracks genuine triangle availability separately from final `modelLoaded`. After FST material replacements and entity texture overrides finish, the same normalized hierarchy is committed into the actual entity content. Native material/alpha handling and shader readiness still determine final visibility. No material cloning or geometry duplication is needed for the stage.

Ownership is transactional. Before commit, the stage owns only the detached wrapper and collision publication, not model geometry/material/texture resources. Root replacement or session cancellation revokes the stage without disposing borrowed loader resources. A failed image-completion wait or FST mapping releases those resources through the existing loader ownership. A successfully returned model that arrives after cancellation is discarded by the scheduler. After commit, the actual entity root owns the same model and normal disposal releases it. Withdrawal is conditional on the same entity root being current, so a stale callback cannot remove a newer root's collider.

## Verification of the proposed patch

The prototype World patch is based on the separate cache/queue patch, not the older complete material source. Its hunks must be merged into the latest source independently. The original worktree and running services were not changed.

```sh
node node_modules/typescript/bin/tsc --noEmit
node --import tsx --test --test-isolation=none tests/model-geometry-stage.test.ts tests/world-model-geometry.test.ts
```

Type checking passed in an isolated staged source overlay. Six helper tests exercise genuine normalized Three geometry and BVH capsule grounding, updated native transforms, identical final normalized bounds and hierarchy, loader-versus-root resource ownership, stale callback revocation, and rollback on collision-publication failure. Three additional tests exercise actual World/FST/FBX/BVH methods with a delayed image I/O double: hidden floor triangles are usable before the image completes; root removal withdraws them during the wait; a genuine HTTP403 FST material failure after image completion withdraws them and disposes parsed geometry/material/texture exactly once. The fixture is authored ASCII FBX with an image dependency. Image transport and worker I/O are injected in these Node tests. No GPU/native network or real public-world latency proof is claimed from this test cohort.

A production renderer component test is also prepared in `tests/model-geometry.browser.spec.ts`: it uses a real authored FBX/FST floor and a delayed valid opaque green PNG, checks a genuine BVH and actual WASD grounding while no model is rendered, then checks final texture pixels. Run both Chromium and Firefox after staging is merged. It has not been executed in this restricted agent environment; type checking passed.

The proposed geometry patch was rebased after the complete native render-state source integration: cache-only base World `d4e47f99a3ff465f71a74ef2cda9304248d4afa404633e966429c0d4fc3c0ea8`; staged after `24ca5e8bf28e1b6c243e2d9ffaf33d3e5b53e04bb1833e7fa1d9a5b6016b0548`; patch `3dcd0b4ea92c6265290adac002868ce6c35aa25dc3e83a8aaddb33800435cfb4`. Both rebased overlays passed type checking; four actual cache/queue World regressions passed in each, and all nine stage tests passed again.

## Root integration evidence (2026-10-01)

The source-frozen stage passed 425 component tests, a production build, 32 focused
browser cases and all 34 required repository checks. Actual stock Chromium154
and Firefox156 Hub inputs moved 0.545 m and 0.633 m before textures finished; the
preceding pipeline moved zero. All model tasks finished after 30.072 and 28.941
seconds. Chromium passed four fluid gates; Firefox failed four at about28.8 FPS.
The subsequent SimulationClock integration passed both short actual local-domain
18-checkpoint flows including synthetic bidirectional voice, real object
interaction, collision and rejoin. No 30-minute session was run or required.
Source-specific results remain in STATUS.md and the evidence directory.
