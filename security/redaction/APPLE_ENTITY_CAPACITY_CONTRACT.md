# Apple entity-observation storage capacity and correlation — v002

Additive v002 changes snapshot renderables/scene/drawn to the size of each
observed set's intersection with expectedEntities. Existing production callers
in EntityRenderer render/updateInScene, CullTask, Application and VKBackend read
these exact snapshot fields; unrelated IDs no longer satisfy their count gates.
No logging payload is restored. Under the existing state mutex the calculation
is bounded by three sets of4096 and does not copy sets or allocate intersections.

Tree/renderable observations and expectation replacement remain enabled after
the first legacy handoff has emitted. The once-only emission still lives solely
in takeIOSRuntimeEntityEvidenceIfReady; it no longer freezes correlation counts
after the first observed entity. A replaced expectation recomputes intersections;
out-of-order render-before-tree is retained. Capacity failure remains fail-closed
even after emission. These are observations, not complete world/render acceptance.

The real-header regression includes unrelated IDs, a matching first handoff,
later entities after emission, replacement, out-of-order tree registration and
stale scene generation. Capacity fixtures now supply the matching expectation
for non-tree sets; queued-original-method fixtures seed the SAME entity ID in
both generations so expected filtering cannot hide a broken generation fence.

All four existing runtime correlation sets now retain at most 4096 distinct
keys each, each key at most128 UTF-16 code units. The bulk expectation setter
also rejects more than4096 supplied elements before inserting. These are local
diagnostic storage bounds, not approved world-size or performance budgets.
They do not limit entities loaded, simulated or rendered by the application.

An overlong key or new distinct key beyond capacity disarms this observation,
clears every set/committed/emitted flag and exposes capacityExceeded in the
existing typed snapshot. Partial prefixes/subsets must not become complete
evidence. Existing recorders ignore subsequent data while unarmed. A new begin
clears the capacity flag and advances the existing generation; old queued scene
callbacks still cannot contaminate it. Duplicates at capacity remain harmless.
The source preserves prior internal string identity semantics; it does not add
UUID/origin validation or claim complete allocator/world-input memory bounds.

The focused test compiles the complete actual header with real Qt containers;
it drives every insertion path to exact capacity and one-past, oversized keys,
bulk exact/overflow/partial-prefix, stale generation, reset and original once-only
handoff behavior. The existing whole queued updateInScene test and raw Qt/OS
diagnostic tests remain unchanged. Baseline source must fail at missing overflow
invalidation. No platform-owned consumer is edited.

Requires existing Apple scene-generation/v002 and configuration/privacy header
prerequisites. This is only a structured-evidence prerequisite: trusted expected
set identity/completeness, non-scene generation fences, native source/artifact/run identity,
private transport, GPU/pixels and the five legacy acceptance consumers remain
pending. Do not interpret zero counts after disarm or a fixed log event as PASS.
