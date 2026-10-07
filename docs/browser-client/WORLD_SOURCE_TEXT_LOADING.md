# Session-owned world source text loading

Actual Hub captures showed repeated FST, baked-material JSON and texture-metadata
requests after admission. The browser now coalesces immutable raw UTF-8 source
text at exact authorized gateway routes. Each consumer still independently
parses materials and owns its textures, sampler settings and geometry. HTTP
material fragments select definitions after parsing and therefore share the
fragment-free HTTP body; queries and ATP fragments remain distinct.

The cache belongs to one World and one actual connected-session approval
generation. Production captures the exact session, connection epoch, approval
object and permission revision before each read, checks it during the producer
and after delivery, and disposes previous generations. Transient reconnect
clears source values synchronously. A rejected approval never accesses a hit.
There is no global cache, localStorage persistence or shared cross-user key.

Limits:512 ready entries,8MiB charged UTF-16 values plus exact route keys,32
pending routes and256readers. Routes are bounded at65536units, accommodating
percent-encoded valid4096-unit native asset addresses. Texture metadata remains
limited to64KiB encoded bytes; FST/material sources to1MiB. A bounded growing
byte buffer copies stream views immediately, refusing oversized/invalid UTF-8
bodies. It retains neither an unbounded chunk array nor arbitrary backing
buffers. The unchanged30second deadline cancels an owned stalled producer.
A canceled consumer cannot cancel its sibling; ended generations cannot
replace a new same-route result. HTTP failures retry normally.

The first128-entry experiment produced397hits but330evictions while retaining
only~0.13MiB at task readiness. The final512-entry policy preserves the same
8MiB byte ceiling and eliminated that measured small-document churn. This
is an explicit capacity decision from the real working set, not a relaxed
render-quality, movement, privacy or test acceptance threshold.

The final CPU checkpoint passed602component tests, including actual loopback
HTTP coalescing, mutable one-byte stream views, Unicode keys, exact route/query
contracts, bounded deadlines, LRU/key charging and genuine session reapproval.
The production build passed after correcting an implicit-any test callback.

Commands from browser-client:

```sh
npm test
npm run build
```

Actual stock Chromium/Firefox Hub cohorts remain the loading/performance
acceptance. Record their frozen source/distribution hashes and aggregate
requests. Model task readiness includes failed tasks and is not complete
success of every texture. Do not equate overlapping phase sums with elapsed
wall time, GPU time or CPU time. Native FBX original textures remain admitted
when later FST material mappings replace them; omission is separate unproven
work and has not been activated.

## Short actual stock Hub cohorts

The final permission-bound512-entry implementation reached zero cache evictions
with319ready documents in389582chargedbytes. Firefox recorded532hits; Chromium
536hits. Across each join/rejoin pair, FST/metadata/materialJSON requests were
190/266/182, compared with492/524/686 in the earlier Image-role Firefox cohort.
Native geometry and image sources remain unchanged. Chromium passed all four
unchanged fluid gates (after walking43.1FPS,34ms p95); Firefox failed all four
(after walking25.9FPS,72ms p95), despite successful native movement and reconnect
within0.74mm. Different live snapshots and actual engine drawing-buffer sizes
remain explicit; no isolated causal whole-world latency improvement is claimed.
[All five frozen actual cohorts](evidence/hub-source-text-runtime-20261001.json)
include the preliminary128-entry experiment and earlier Image-only baseline.
