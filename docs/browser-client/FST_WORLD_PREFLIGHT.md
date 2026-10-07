# FST admission preflight: preserve geometry-first Hub loading

Substantial AI-assisted implementation. This runtime change is reviewed and integrated on the browser topic branch; actual live results are recorded separately.

Actual offline public Hub cache evidence found no original Texture nodes in92 inspected baked models. A template-first rewrite would defer real geometry/BVH publication until required replacement images finish without omitting any original request. This preflight therefore obtains the existing per-world prepared FBX bytes under the exact same authorized resolver, producer, worker limits and reader signal BEFORE starting original images. The common preparation method is moved intact and reused; the child borrows that same immutable prepared buffer, with no second HTTP request/preparation/cache registration. CPU phases remain counted inside the single producer. The original prepared owner still leases embedded sources.

Zero-texture, unknown/unsupported graphs and plans exceeding existing row limits preserve geometry-first loading and the original ordered material path. Metadata-only preflight allocates no derived binary buffer. Only graphs with a potentially removable original Texture read ordered material definitions ahead of the child. All selectors/definitions must conservatively prove a removable consumer before successfully authorized actual template images can be loaded first. Unsupported fallthrough, custom fields, transforms, occlusion/gloss maps, unmatched selectors and shared surviving consumers keep original images and geometry publication. Successful actual templates are still required before omission, and the final derived-graph helper repeats the complete proof. Nested FST remains unchanged. Parsed definitions may be reused on fallback; image/template creation still follows the old order. Original reader/cache/resource/abort limits are preserved.

The optional internal prepared argument comes only from this exact FST child, not asset properties or userData. Approval snapshot checks surround preparation, graph inspection, definitions, templates, parsing and assignment. Invalid preflight-only metadata falls back to the unchanged parser; authority/cancellation never becomes success. Existing preparation/parser validation still fails invalid resources. Source graph uncertainty is not permission to drop textures. Timing aggregates add fstGraphPreflight and fstTextureAdmission without exposing URLs/IDs.

## CPU verification

43 candidate cases passed:5 new actual BrowserWorld order cases,4 metadata preflight cases,10 actual World admission/resource cases,6 staged geometry,5 cleanup,4 cache and9 parser cases. Full candidate TypeScript passed. The new zero-texture fixture models the real Hub graph pattern and asserts actual parsed six-vertex geometry publication BEFORE a deliberately unresolved required replacement image; it also proves exactly one fetch/prepare, final model identity and immutable cached bytes. Unknown valid-Three IDs, fallthrough, unmatched and eligible plans test the alternative orders. Unknown direct FBX denial retains original image admission/BVH cleanup; invalid materialMap syntax still rejects without allocating a parsed model. Actual template failure now occurs AFTER necessary immutable-byte preflight but before original image admission; tests explicitly distinguish these boundaries.

Failed initial test assumptions were corrected, with unchanged semantic checks: the old fetch ordering assertion conflated immutable FBX preparation with original image admission; a deliberately malformed empty-name string node was also invalid to Three itself, so the unknown-graph success control uses a valid negative-ID metadata object that the conservative inspector refuses. No invalid resource was made accepted. Runtime GPU tests and a source-bound native/Hub cohort remain required; no speed/byte improvement or native parity is claimed.

Commands: `node --import tsx tests/world-fst-preflight.test.ts`, `node --import tsx tests/fst-admission-preflight.test.ts`, plus the existing World/parser suites and `node node_modules/typescript/bin/tsc --noEmit`. CPU preparation did not start native/browser services; actual GPU/network evidence is recorded separately.

The integrated preflight passes all8 actual Playwright WebGL2 cases in both
engines (23.2seconds), with exact final pixels and unchanged fixed camera/pose.
[Curated proof](evidence/fst-preflight-gpu-20261001.json). This establishes authored
network-image admission and World rendering, not native/Hub loading latency.


## Exact-buffer graph memoization

The subsequent integrated per-World WeakMap inspects each immutable prepared
buffer identity once for zero/unknown original-texture graphs. These results
retain only tiny sentinel values, with no parsed tree. Positive graph trees use
WeakRef and safely reparse if collected. Final admission reuses the same owned
memo, while each FST consumer still checks its current authority and owns its
mutable geometry/materials independently. Six simultaneous real mapped parses
prove one fetch/preparation/inspection for zero, unknown and positive fixtures;
revocation cannot consume a stale memo result. Disposal and detached-buffer
refusal are covered. The full integrated component suite passes729/729, including
the existing real localhost HTTP source-cache test which was unavailable to the
restricted proposal agent.

All8 actual rendering/admission WebGL2 cases passed again after integration in
both engines (22.4 seconds), with exact final RGBA and no camera/pose changes.
[Source-bound memo evidence](evidence/fst-graph-memo-gpu-20261001.json).
Fresh unchanged-quality short stock-browser Hub cohorts now confirm 97 exact-buffer
inspections and 144 memo hits, with no original image omission. First observed
complete model readiness is 22.7 seconds in Firefox and 23.8 seconds in Chromium;
three-second observation intervals limit precision. Functional movement, native
position replication and reconnect pass. Firefox fails all four fluidity gates;
Chromium fails one reconnect walking stall gate (250.2 ms against 250 ms).
[All three retained cohorts](evidence/hub-fst-memo-capabilities-runtime-20261001.json).
Live domain snapshots and different device density prevent an isolated causal
latency claim; overlapping phase totals are not session elapsed time.
