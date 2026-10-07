# Prepared FBX cache and bounded model admission

This integration is a separate loading cohort after the native material/render-state cohort. Its patch is based on `world.ts` SHA-256 `b47b3cb725faa126beb9b74c257e15d46433c57305604b5ccc5c03349910d357`; the prior native render-state/material integration is retained in full, and only loading/cache/queue hunks are changed.

The browser resolves each FBX source to its exact authorized asset route before selecting a session-local prepared-byte cache entry. Concurrent models share the fetch and full worker preparation. Their final Three FBX parsing, geometry, materials, texture samplers and transforms remain independent. The producer records material-binding and Draco CPU phase durations once. Each reader records its own wall-clock preparation wait, including cache hits. Cached output is borrowed without transfer or mutation; raw inputs and parsed Three objects are never retained by this cache.

The scheduler admits six model loads. Arrival bursts request one drain microtask. A full scheduler does not evaluate priorities or sort pending models. When capacity opens, the current entity-map collider bounds and current root center distance are evaluated once per request; equal priorities use FIFO. Every sixth dispatch selects the oldest remaining request, allowing distant geometry to make progress during nearby arrivals. Pending metadata is bounded by the protocol's 100,000-entity ceiling. No active job is canceled to promote another model.

Replacing or removing an entity revokes its own reader. A queued load cannot start after revocation; an active load retains its capacity slot until its underlying promise settles. Shared FBX work survives another reader's cancellation; the last pending reader immediately revokes the fetch/preparation. Model dependency managers and the FBX texture-completion wait receive the per-reader signal. A successful late model result is disposed instead of attached. Session termination revokes all producers, active readers and queued admissions.

Already-started FST material-factory image/alpha dependencies retain their existing world-scoped cancellation in this cohort; a canceled reader stops later assignments and releases any completed material. Optional per-reader propagation through those material helpers is a separate change. Avatars retain their existing world-scoped model loading. No geometry-before-texture staging, mesh visibility or collision behavior is changed here.

## Verification

The integration was tested in an isolated writable source overlay, without changing the protected original worktree or starting a network/GPU service:

```sh
node node_modules/typescript/bin/tsc --noEmit
node --import tsx --test --test-isolation=none tests/model-load-scheduler.test.ts tests/prepared-fbx-cache.test.ts tests/model-fbx-pool.test.ts tests/native-baked-fbx-fixture.test.ts
node --import tsx --test --test-isolation=none tests/world-loading-cache.test.ts
```

Type checking passed. The scheduler/cache/pool/authored-Draco suite passed 32 tests. Four additional tests exercise the actual World load/remove methods and actual Three FBX parsing: one authorized preparation with distinct model objects and CPU counts; independent reader cancellation versus last-reader fetch cancellation; actual entity removal revoking its active model before root disposal; native position-only updates while six slots are occupied reranking the next queued model by current bounds. All four actual World regressions passed in both the cache-only and staged overlays. Fetch and the worker transport were injected I/O for these Node tests; the model bytes were authored valid ASCII FBX. These tests do not establish GPU performance or public-world loading improvement. The parent integration must run the real Hub cohort against the final merged source and record exact bundle/runtime hashes.

Rebase validation: before World `b47b3cb725faa126beb9b74c257e15d46433c57305604b5ccc5c03349910d357`; cache-only after `d4e47f99a3ff465f71a74ef2cda9304248d4afa404633e966429c0d4fc3c0ea8`; patch `38fd33bf0634b276b319a7c0e2e75b56ebd1d62f82294973d5bce15458d45d32`. The original source hash was unchanged after validation, and `git apply --check` passed against it.
