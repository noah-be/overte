# Opt-in native avatar diagnostics

## Current same-flight transport fields

The diagnostic successor uses strict inner flow version 2, adding required
nullable `transport` and `otherWrite` fields to the ten keys described below.
Gateway-log sample version 2, native-child sample version 1 and author version 1
remain separate source roles. Old inner flow-1 artifacts require their exact
frozen decoder; they are refused by current projection without backfill.
The flow-1 description below records the published `39ff99ac` boundary.
Published `39ff99ac` results used inner flow 1; fresh actual measurements
of inner flow 2 remain required. Integrated source gates now pass; those
measurements are still pending.

| Field | Values, in order |
| --- | --- |
| `transport` | readyState 0..3 or null; current buffered bytes or null |
| `otherWrite` | class; serialized UTF8 bytes or null; original pre-write buffer or null; captured native-message timestamp or null; diagnostic binding owner |

Transport exists only with a held physical flight. Two sequential socket getters
are measured at an existing unthrottled snapshot opportunity and guarded by the
captured token, sender epoch, pending slot, sender and flow identities. Reentrant
replacement refuses the whole snapshot; unavailable measurements remain null.
These are local sequential properties, not an atomic kernel view or remote ACK.
The 64 MiB observation cap does not alter the original 4 MiB admission predicate.

Generic classes are 0/state, 1/entities or entityUpdates, 2/Tablet and 3/other.
Recognition uses only the fixed leading serialized type; other key orders remain
other. Metadata is committed after the actual generic send returns, from the
same original single serialization and captured pre-write buffer. Invalidation,
close or a reentrant binding/epoch change refuses its commit. Registration occurs
only after the existing approved managed permission branch; default-off/public
paths create no binding or byte scan. Existing send errors, undefined payload,
method lookup and observer order remain. Binary PCM is excluded.

The reused timestamp is captured at generic entry from the last native message;
it is not actual write or callback time. Owner 0/current or 1/retired describes
the socket diagnostic binding at snapshot, not proven original caller/message
authority. One last generic witness cannot account for all traffic or establish
buffer origin. UTF8 counting scans the existing serialized text before applying
the nullable byte-size cap; no separate fixed diagnostic CPU-work cap is claimed.
The sampled getters, byte scan and new bookkeeping have explicit observer cost.
No callback release, timer, transport repair or causal inference is added.

At exact `39ff99ac902b22eb84b732b2cba2ae61e47ab9e5`, automatic run
37192753251 and single opt-in 37193186302 each fail the unchanged movement
checkpoint after four of eighteen Core checks; owned stop passes. The opt-in
artifact retains 38 native and 118 gateway rows without offline rejection or
censoring. Target-bearing ingress and validated target pending assignments
coexist with an old-pose physical flight of 26158 bytes. That held slot motivates
current queue measurement; it does not explain its cause or prove channel
continuity across sampled rows. Later Core voice/interaction/rejoin are not run.

The sender and collector remain byte-identical `39ff99ac`. Current private
viewer source meanings stay fifteen runtime identities and three Git-only
identities, with collector as the third Git-only dependency. Frozen old viewers
remain bound to their old schema/source; no missing identity is backfilled.

## Received envelopes, send slots and callbacks

The reviewed diagnostic successor distinguishes a received avatar envelope,
complete serialized pending assignment, observed write invocation and matching
local send callback. It changes no native wire message, approval decision,
socket capacity predicate or Core movement deadline. The Native bridge and
sampler remain unchanged. Diagnostics stay disabled by default and are limited
to the owned managed-domain path.

Native log samples remain version 1. Gateway log samples use version 2 and
require a nullable `gatewayAvatarFlow` field. The collector chooses the strict
projector modes `native-child` and `gateway-log` from the fixed filenames
`native.log` and `gateway.log`. It never chooses a version from a row or backfills old gateway
rows. Historical artifacts retain their exact frozen decoder. Current private
viewer meaning includes the collector as a third Git-only dependency; the
fifteen runtime source paths and key set are unchanged; the four reviewed
production source hashes change.

Flow version 1 has ten fixed keys: `version`, `at`, `sequence`, `censored`,
`counts`, `ingress`, `offer`, `flight`, `pending` and `callback`. Compact tuples
have these meanings:

| Field | Values, in order |
| --- | --- |
| `censored` | saturated counter; exhausted observation budget |
| `counts` | ingress; offer entry; pending assignment; offer refusal; thrown offer; observed write; successful callback; failed callback; invalidation |
| `ingress` | original receive time; fixture target distance; approval; connected; current native association |
| `offer` | outcome; last validated receive time; last validated target distance |
| `flight`, `pending` | original receive time; serialized byte size; target distance; current or retired owner |
| `callback` | original receive time; serialized byte size; success or error; current or retired owner |

Outcome codes are 0/no recorded outcome, 1/pending assignment, 2/refusal and
3/exception. Owner codes are 0/current and 1/retired relative to the emitting
session and original item epoch. Callback codes are 0/success and 1/error.
Unknown target distance or memory facts remain null. Ingress is observed before
approval filtering; it does not admit the envelope. Pending assignment is
observed before pumping and does not prove successful offer return. Write
observation follows the existing send invocation, while a synchronous callback
can precede it. Neither callback completion nor write observation proves
browser receipt.

Counters include only observed managed diagnostic events over the physical
channel lifetime. Rows carry no channel identifier, so an artifact alone cannot
prove continuity across rows. They are not per-generation totals or conservation equations.
They saturate at 65535. Revocation clears cached ingress and offer state, while
an already issued physical write and bounded counters retain their lifetime.
Snapshots use the existing receive timestamp, at most 128 observations and
500 ms spacing. A terminal censored snapshot clears all measurement fields to
null. Cached snapshots can accompany later native rows; those rows do not
identify the same envelope or establish clock alignment.

The original 16 KiB line, 512-row, 1 MiB tail/output and avatar text limits
remain. Worst-sized legal rows can still exceed the combined output cap and
refuse; finite diagnostic tuples do not promise full retention. No raw pose,
identifier, URL, cookie or error text is exported.

Exact `1f7950b2` automatic run 37185774127 passes all 2930 product and 130
Chrome UI cases, while native Core retains its original movement failure.
The single opt-in run 37186294900 also fails movement: 79 attached write
witnesses have an empty pre-write buffer, but five native target samples attach
an earlier old-pose witness. No target-bearing gateway write was observed.
That result does not distinguish received content from a held physical slot;
the successor measures that boundary rather than claiming a movement repair.

## Complete-avatar scheduling and source identity

Avatar delivery now retains one physical send and the newest complete unsent
snapshot per browser socket. It uses the original 4 MiB admission threshold;
non-avatar senders, world overflow, audio and Tablet policies keep their
existing paths. Queued snapshots capture serialized state and its original
native-message time, approval revision and native/session generation.
Revocation clears queued authority; an already issued physical write remains
in flight until its callback. A failed physical channel closes its current
owner even across a same-socket rejoin. No retry timer or partial avatar/joint
truncation is added.

A delivery witness records the selected complete snapshot's actual attempted
send and original receive time. An offer queued behind a physical write is not
a refused send. Existing512-row, 128-observation and 500 ms bounds remain.
Latest-state replacement may deliberately omit intermediate poses; it does
not prove browser receipt. Current source evidence adds the new
`gateway/avatar-snapshot-sender.mjs` producer:15 runtime source identities.
The exact `1f7950b2` viewer has two Git-only fixture identities; the successor
adds the collector as described above. Old14+2 and15+2 artifacts remain on their
frozen decoders; missing identities are refused without backfill.

Exact9e negative evidence shows four distinct target-bearing observations
blocked above4 MiB; the native target is correct and the browser peer is stale.
A real own-WebSocket regression reproduces old failure within the original
2800 ms wait and passes the bounded complete-state scheduler. This is
loopback/source evidence, not a substitute for fresh actual native Core.

## Delivery witnesses

Current opt-in samples add `nativeDelivery` and `gatewayDelivery`; absent
observations remain null. Native counters record queue, refusal and socket-write
invocation branches over the helper lifetime, saturate at 65535 and expose
censoring. They do not establish write-return acceptance or remote delivery.

Gateway stores at most 128 observations per session, separated by at least
500 ms using the existing native-message timestamp; it adds no clock or timer.
Each observation records the open/buffer/write branch and the fixed fixture
target distance from an already captured envelope. The latest stored snapshot
can be attached repeatedly to existing projected sample rows. Thus more than
128 rows can contain a witness without exceeding the storage bound. No extra
row consumes the original 512-row projection budget. The snapshot has its own
ordinal and timestamp, can be stale, and does not identify the same envelope
as the accompanying native row. Unknown buffers remain null; finite buffers require the exact
open/below 4 MiB write predicate. Saturation and avatar-projection censoring remain
explicit.

Core `socketSelection` identifies the selected and latest-created WebSocket
using only bounded ordinals and fixed readiness enums, with censoring after 32
sockets. It adds no socket URL, identifiers or raw positions. It observes the
original raw-snapshot selection rather than changing it. Latest-created does
not prove current admitted session; readiness is observed at Core capture, not
at message arrival. Default-off execution allocates no delivery state. All
original movement assertions and waits remain.

Use the exact current projector for current artifacts. Older artifacts require
their frozen decoder; missing new fields are refused, never backfilled. These
witnesses distinguish unobserved forwarding and socket-selection boundaries;
no individual witness proves end-to-end delivery or acceptance.

Current V26 product/build/fixture/repository code checks pass; the
[source proof](evidence/avatar-delivery-angle-source-checks-20261004.json) records
all 2874 product tests without skips and the separate failed nine-service
preflight. Registered Native was missing while the other eight births matched.
The cause is unknown; no restart or native/session acceptance is claimed.

Use the existing Browser client workflow's manual `avatar_sample_diagnostics`
input to investigate a native peer's stale browser pose. It defaults to false.
The normal workflow and all original core-journey assertions remain unchanged.

```sh
gh workflow run browser-client.yml --repo noah-be/overte \
  --ref feature/main/browser-client \
  -f startup_diagnostics=false -f avatar_sample_diagnostics=true
```

Dispatch only after reviewing the exact source and confirming the fork/ref. The
input enables the existing full sampler before isolated laboratory preparation.
Startup-only diagnostics omit this sampler and its collector. This is a
controlled managed-domain measurement, not public-world or device acceptance.

After the original stop and evidence curation steps, the workflow adds
`native-avatar-samples.json` to the existing `native-core-journey-evidence`
artifact. The collector uses the current reviewed production projection and only the
last 1 MiB and at most 512 accepted rows of each owned native/gateway log. It
discards incomplete lines and reports offline tail and row censoring explicitly.
An uncensored retained log does not establish the sampler or live projector's
internal budget: native print/output loss or a caught projector emit failure can
consume those separate limits without creating a retained row. Missing later
rows therefore do not prove absent production, simulation or packet delivery.
The collector refuses unsafe files or metadata changes rather than exporting partial raw data.
No raw log, path, avatar name, session identifier or credential is included.

Compare publication pose age, rig phase/timing, post-publication pose delta and
receiver position counters with the retained failed core journey. A recently
arrived browser snapshot does not establish when its native pose was sampled.
Two projected sources can overlap; their counts must not be added as independent
observations. Full sampling has observer overhead, and neither Stats freshness
nor native packet delivery is established by these counters alone.

The expanded sampler also records `peerSimulationRateHz`,
`authorGlobalPositionOutboundKbps` and `authorLocalPositionOutboundKbps`.
Missing capabilities or invalid readbacks remain null; zero remains zero.
Simulation counts receiver simulation entries, and the outbound fields measure
encoding work. Neither proves delivery of the commanded coordinates. Native
rate getters can roll their averaging intervals, so these observations have
that bookkeeping effect. The simulation getter also returns zero when its
native avatar lookup is absent; its averaging window, personal mute and update
scheduling remain alternatives to budget starvation. A zero value alone does
not establish that cause. Passive mode performs none of these additional reads.
The strict expanded projection refuses old rows without the new fields. Replay
historical artifacts with their exact frozen projector; do not reinterpret them
using current source.

The Core movement diagnostic keeps three separate time references:
`commandIssuedAtMs` is the matched command's existing Node timestamp/sequence,
`commandAppliedAtMs` is the participant's existing reported timestamp, and
`diagnosticReadAtMs` is the existing Node readback time. The projection adds no
clock call, wait, file read or retry. Invalid or unavailable references remain
null. The original 2800 ms wait starts after the awaited command-file write, rather
than at the later native application event. The existing issued timestamp is
captured before that write; issued and diagnostic-read are Node wall clocks,
while native apply and observation use the separately scoped native wall clock. Gateway sample offsets measured from
that native event do not establish alignment with the browser capture or
synchronized producer clocks. These diagnostics cannot change the captured
movement assertion or turn a failed journey into acceptance.

Offline replay against an already stopped, owned private laboratory is:

```sh
node browser-client/tools/curate-avatar-samples.mjs \
  --output /absolute/owned/evidence-directory --commit-sha FULL_TESTED_SHA
```

Run from the repository root. The input root is fixed to `build/browser-lab`;
the output directory must already exist and be owned and protected against
group/other writes. Publication is exclusive and refuses an existing output.
This command starts no browser, native process, domain or service. Its report is
diagnostic evidence and cannot turn a failed acceptance assertion into a pass.
