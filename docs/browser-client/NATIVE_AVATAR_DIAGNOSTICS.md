# Opt-in native avatar diagnostics

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
