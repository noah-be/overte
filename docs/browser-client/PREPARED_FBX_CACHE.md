# Per-world prepared FBX byte reuse

`PreparedFbxCache` deduplicates pending preparation and retains completed, prepared FBX bytes. It stores neither raw downloads nor parsed Three objects. Each model still gets its own Three hierarchy, materials and sampler state.

The caller must authorize the exact source before entering the cache. Cache keys remain exact, including query parameters; no URL normalization, cross-world sharing or authorization inference occurs. The class is owned by one world and its abort signal. Keys may contain up to 65,536 code units so a valid 4,096-code-unit Unicode asset URL remains valid after gateway query encoding.

Bounds are 64 ready entries, 128 MiB of ready buffers, 16 pending keys and 256 pending reader records. LRU eviction limits completed bytes and entries. Pending keys plus ready keys retain at most 10 MiB of UTF-16 key data. Output larger than the ready budget may be delivered to current readers within the preparation pipeline's 256 MiB limit, but is not cached. Only the two numeric CPU phase fields are retained from producer metadata.

`get(key, producer, readerSignal)` gives the producer its own `AbortSignal`. One reader can leave without canceling other readers. Removing the last pending reader aborts the producer, which must forward that signal to its download and `BakedFbxPreparePool.prepare` call. Whole-world cancellation aborts all producers, rejects every reader and clears ready bytes. Generation checks ignore late producer results and prevent revoked work from starting in the producer microtask gap.

Returned buffers are borrowed read-only for parsing: never transfer or mutate cached prepared output. The cache detects accidentally detached output on the next lookup and removes it. Phase records are copied separately for each reader. Actual CPU phase accounting belongs inside the producer once per preparation, rather than after each cache hit. `cacheHit` indicates reuse of either ready bytes or an existing producer; statistics separately report hits, misses, ready bytes, pending keys, readers and evictions.

```sh
cd browser-client
node --import tsx --test --test-isolation=none tests/prepared-fbx-cache.test.ts
```

Fourteen Node tests cover shared cancellation, genuine pool-API cancellation with an owned worker double, late generations, world abort, ready-delivery races, bounded keys/readers/bytes, LRU, failures and the actual gateway URL encoding function. They establish lifecycle and memory ownership contracts, not browser speed. World integration and incremental real-world loading measurement remain pending completion of the preceding measured cohort.
