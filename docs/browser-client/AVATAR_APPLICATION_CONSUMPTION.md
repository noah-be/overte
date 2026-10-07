# Avatar application consumption

The browser requests `avatarConsumption: "ack-v1"` when joining. An updated
gateway confirms this mode in a session-bound state message and publishes the
actual sender epoch and validated permission revision before admitting avatar
delivery. Approved snapshots may arrive before the native connected state;
connection readiness is not substituted for permission approval.

Each complete avatar snapshot carries a five-field `delivery` descriptor:
version 1, session identifier, permission revision, sender epoch and increasing
sequence. The browser validates it before application delivery. Main returns
literal `true` only after synchronous World avatar state application and stats
update complete. The compressed-asset session preserves this return value.
Only the captured current socket can then send `avatarConsumed` with that exact
descriptor. This is application consumption, not a GPU, asset-loading or native
movement acknowledgement.

The gateway retains one physical write and the newest complete pending snapshot.
In negotiated mode it additionally holds an application credit for the issued
snapshot. A successful socket send callback releases only the physical write;
the current browser acknowledgement releases only application credit. Either
may arrive first. Both must finish before the next complete snapshot is sent.
The issued and pending snapshots remain bounded by the existing count and byte
limits. No credit timeout, retry, partial-pose merge or forged send completion is
introduced. Missing application consumption holds one credit and replaces only
the latest pending snapshot until actual acknowledgement or session retirement.
Audio, entities and Tablet traffic still share the WebSocket.

Revocation invalidates pending data and old logical credit while retaining any
real outstanding socket callback. New state messages bind the browser to the
actual post-invalidation epoch and exact approval. Stale/replayed descriptors,
reentrant duplicate application and acknowledgements from another owner are
refused. A retired callback cannot acknowledge or report an error against a
newly joined session. Current protocol failures close the owned socket with
application code 4002. A late physical write failure still retires its current
socket owner through the existing gateway failure path.

Compatibility is explicit. A visitor that does not request the capability uses
the previous callback-driven gateway path. An older gateway that confirms no
capability keeps the new browser in legacy mode. Unknown capability values or
mixed negotiated delivery metadata fail closed. This is a gateway/browser
protocol update; native Overte clients and domain transport are unchanged.

The [current source evidence](evidence/avatar-consumption-source-checks-20261004.json)
records 3057 complete product cases, production and fixture builds, and 34
repository suites. Independent corrected source/mock checks preserve all old
assertions and demonstrate four desired failures on the original private
prototype followed by four passes. The real owned loopback fixture separately
contrasts callback-only backlog with application credit under controlled slow
consumption and the original 2800 ms limit. It is not a hosted cause or a
Chrome/native acceptance result. The [status](STATUS.md) retains the earlier
actual movement failures and records the next exact-source qualification.

V30 production preparation uses the exact current manifest at
`browser-client/tests/fixtures/capture-avatar-consumption-v30-complete-source-manifest.json`.
The preparer accepts one digest and imports no historical reader. Its nine
whole-before CPU inputs and finite source normalization retain the unchanged
history and physical-reader limits. Historical test success does not admit an
old source tree to production or replace actual current protocol tests.
