# Apple entity-observation storage capacity

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
prerequisites. This is only a structured-evidence prerequisite: expected-entity
intersection, non-scene generation fences, native source/artifact/run identity,
private transport, GPU/pixels and the five legacy acceptance consumers remain
pending. Do not interpret zero counts after disarm or a fixed log event as PASS.
