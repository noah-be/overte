# Per-world prepared FBX byte reuse

`PreparedFbxCache` deduplicates pending preparation and retains completed, prepared FBX bytes. It stores neither raw downloads nor parsed Three objects. Each model still gets its own Three hierarchy, materials and sampler state.

The caller must authorize the exact source before entering the cache. Cache keys remain exact, including query parameters; no URL normalization, cross-world sharing or authorization inference occurs. The class is owned by one world and its abort signal. Keys may contain up to 65,536 code units so a valid 4,096-code-unit Unicode asset URL remains valid after gateway query encoding.

Bounds are 128 ready entries, the unchanged 128 MiB of ready buffers, 16 pending keys and 256 pending reader records. Ready UTF-16 key data additionally has an explicit 8 MiB budget; entry, buffer and key limits independently evict the least recently used ready entry. LRU eviction limits completed bytes and entries. Ready keys retain at most 8 MiB of UTF-16 key data; the unchanged sixteen pending keys add at most 2 MiB. Key byte accounting is released on eviction, detached-buffer refusal and disposal. Output larger than the ready budget may be delivered to current readers within the preparation pipeline's 256 MiB limit, but is not cached. Only the two numeric CPU phase fields are retained from producer metadata.

`get(key, producer, readerSignal)` gives the producer its own `AbortSignal`. One reader can leave without canceling other readers. Removing the last pending reader aborts the producer, which must forward that signal to its download and `BakedFbxPreparePool.prepare` call. Whole-world cancellation aborts all producers, rejects every reader and clears ready bytes. Generation checks ignore late producer results and prevent revoked work from starting in the producer microtask gap.

Returned buffers are borrowed read-only for parsing: never transfer or mutate cached prepared output. The cache detects accidentally detached output on the next lookup and removes it. Phase records are copied separately for each reader. Actual CPU phase accounting belongs inside the producer once per preparation, rather than after each cache hit. `cacheHit` indicates reuse of either ready bytes or an existing producer; statistics separately report hits, misses, ready bytes, pending keys, readers and evictions.

```sh
cd browser-client
node --import tsx --test --test-isolation=none tests/prepared-fbx-cache.test.ts
```

Fourteen Node tests cover shared cancellation, genuine pool-API cancellation with an owned worker double, late generations, world abort, ready-delivery races, bounded keys/readers/bytes, LRU, failures and the actual gateway URL encoding function. They establish lifecycle and memory ownership contracts, not browser speed. World integration and incremental real-world loading measurement remain pending completion of the preceding measured cohort.

## Count-limit proposal qualification

The recorded initial admissions reach the old 64-entry limit while retaining
only approximately 10–11 MiB of prepared buffer bytes. The older captured pair
has eight repeated FBX source URLs per initial admission; the newer native-slot
pruning pair has eight and ten. This is separate from metadata caching: initial
FST/texmeta/material JSON URL duplicates are already zero in the older pair.
These cardinalities support a bounded 128-entry candidate, not arbitrary cache
growth. The fixed owner/Map record maximum doubles from64 to128; no stronger
total-memory claim is made. The unchanged payload budget remains128MiB.

A portable counterfactual executes the actual cache methods after changing only
the count constant back to64. An authored workload of123 distinct32KiB byte
preparations followed by8 old-key repeats produces131 preparations under64
and123 under128, with identical borrowed buffers on all8 candidate hits. The
order is controlled; it is not a replay of private Hub source addresses.

The tests preserve the original entry-bound/LRU test at the new128 boundary,
the original128MiB payload eviction/non-cacheable-output tests, and every
pending-reader/abort/generation/detachment/producer contract. Additional tests
cover the exact8MiB UTF-16 key boundary using supplementary Unicode, eviction
accounting, oversized single keys, detach/replacement and idempotent disposal.
The pre-existing authorized source lookup and read-only buffer borrow call site
are unchanged. No parsed Three hierarchy, texture sampler, collision resource,
account or cross-world resource is shared.

The safe evidence reports each admission independently and pins all protected
raw report hashes. Repeated response-duration sums include original responses,
repeat responses and overlap. Uniform-length repeated-byte estimates are
explicitly estimates. Neither these measurements nor the CPU control establishes
a whole-Hub loading/FPS improvement. Root owns the actual current-source
comparison; no GPU/native/browser/domain/network test was launched for this
candidate.

```sh
node --import tsx --test --test-isolation=none tests/prepared-fbx-cache.test.ts tests/prepared-fbx-count-cap.test.ts
npx tsc --noEmit
```

## Actual stock-Hub cache128 qualification

[Measured comparison](PREPARED_FBX_CACHE128_MEASURED.md) and its
[aggregate evidence](evidence/prepared-fbx-cache128-measured-20261002.json)
record both actual joins per engine with82 exact pins. Firefox same-session
FBX duplicate responses fall10/9 to0/0 and successful worker preparations
131/130 to122/122. Chromium duplicates fall8/10 to1/1 and preparations
130/131 to122/122. All ready endpoints have122 entries,40,449,509 charged bytes,
46,940 key bytes and zero evictions, within128MiB and8MiB limits.
Chromium retains all four fluid passes; Firefox still fails required gates.
This establishes reduced repeated FBX work, not a causal texture/network/
end-to-end speed gain or general browser fluidness.
