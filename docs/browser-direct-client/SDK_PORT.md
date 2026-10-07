# Native protocol port

The browser vendors the required TypeScript import closure from the Apache-2.0
Vircadia Web SDK at `35cb07ba5d4a7e06d078d762fcd4584099a26959` (package
`2024.1.2`). Original source paths, Git blob IDs, and content hashes are in
`browser-direct-client/vendor-sdk.json`. Original copyright/license headers are
retained. The SDK's original capture/worklet implementations are omitted because
the local browser audio module owns microphone consent, capture, and playback.
The manifest distinguishes exact, adapted and omitted inputs, records current
adapted hashes and explains each change. `npm run verify:sdk` checks the complete
vendored inventory and modification notices; `node tools/verify-sdk.mjs --source
/path/to/vircadia-web-sdk` additionally checks all original Git objects.

## Compatibility decision

Unmodified Vircadia Web is not compatible with this Overte revision. Its SDK
uses a different protocol signature, packet versions, attachment-bearing avatar
identity, JSON rather than CBOR entity-query parameters, and historical binary
entity property flags. The current Overte audio-processing dependency provides
no DataChannel transport. Historical signaling source alone is not proof of
working browser connectivity. See `TRANSPORT_RESEARCH.md` for primary sources.

`tools/generate-protocol.py` compiles and executes the production C++
`PacketHeaders.cpp` and Qt metaobject. Its generated browser version/signature
table, source/HMAC header classifications and replicated mapping are checked
against the real C++ implementation, rather than changing the
server's protocol admission rule. At the base revision the signature is
`5622e88718593136a572e50ac20b3ade`.

The browser uses native domain admission, node discovery, service handshakes,
connection-secret HMAC, avatar pose/traits/identity, and PCM audio packets. Avatar
identity serialization removes the deprecated attachment count in accordance
with `AvatarData::identityByteArray` and `processAvatarIdentity`.

Domain discovery reads the production Qt `QHostAddress` discriminator instead
of assuming fixed IPv4 socket lengths. Native STUN fallback can write null
addresses with no address bytes; `Any` is similarly short. Domain UUIDs retain
Qt's big-endian byte order. Shared native/browser fixtures execute the real
`Node` and `SockAddr` stream operators and exercise truncation boundaries.
IPv6 node advertisements are explicitly unsupported by the SDK's current
32-bit address representation; they fail the session with a visible reason.
Anonymous native challenges retain empty username/signature fields. Directory
key generation/upload requires a configured authenticated account and nonempty
username; joining a guest-enabled self-hosted domain does not initiate a write
to the historical SDK's default directory. Server authentication is unchanged.

## Entity projection

The entity server exposes a rendering projection inside its existing process,
through authenticated native packets over its own DataChannel. It uses the
existing canonical entity serializer. The browser never decodes the SDK's
historical binary entity schema and does not issue the old entity query.

Former unused packet slots 91 and 93 are named `BrowserEntityQuery` and
`BrowserEntityData`. Their numeric IDs, versions, packet count, and protocol hash
are retained. This avoids rejecting existing native clients due to an optional
browser feature. Queries and responses use normal sourced/verified packet
headers; a known current agent node and its secret are required.

Schema 1 query: `{"version":1,"revision":"<last SHA-256 or empty>"}`.
The reliable JSON reply contains `version`, `revision`, and `entities` if changed,
or an explicit `error`. Snapshot state is read from the real entity tree; the
browser computes additions/updates/removals against its prior session state.
Queries are rate bounded and reliable snapshots have a 16 MiB limit. Private
user data, server scripts, simulation owner, certificate/marketplace metadata,
and non-domain entity hosts are excluded. Native edits remain subject to the
existing server edit filters and permissions; this projection is read-only.

## Assets and audio

ATP requests use the actual asset server's mapping/get operations over its own
native DataChannel, with verified SHA-256 content. A browser-local ServiceWorker
routes the requesting tab's virtual ATP URL to that same tab's current session.
No HTTP asset gateway or visitor-specific native client is involved. Generation
checks reject stale session requests, and relative model/texture paths retain
their source directories. Asset receive limits and timeouts are explicit.

Audio uses the native 24 kHz rate: 240 PCM16 mono samples per 10 ms microphone
frame and 240 stereo samples per mixer output frame. PCM format negotiation is
native. Synthetic audio and real microphone/device evidence must be reported
separately. Native mixer mute requests stop browser capture immediately.
Mixer silence is delivered as one zeroed stereo PCM frame after validating the
native sample count. Optional native environment and stream-statistics controls
are consumed without retaining stream identifiers; native Zone reverb effects
are currently unsupported.

## Loading and lifecycle

`DomainServerOptions.peerFactory` selects either native Window RTC or a transferred
channel for a DedicatedWorker. The same SDK socket performs native source/HMAC
verification, UDT ACKs, retransmission and message assembly. The Window broker
owns only PeerConnection creation and SDP/ICE controls; it transfers the actual
DataChannel synchronously before the first await or send, as required by the
[WebRTC transfer rules](https://www.w3.org/TR/webrtc/#transfering-a-data-channel).
Datagrams never pass through the broker. Unsupported transfer produces a visible
error. The current renderer-free diagnostic also uses the dedicated session
worker and actual transferred channels; earlier main-owned diagnostic results
retain their historical default-native-factory scope.

Peer acquisition is cancellable and delayed factory/SDP results retain their
generation. Leaving closes owned peers synchronously and waits for an epoch
reset acknowledgment before reconnect can create peers. Control RPC, peer counts,
ICE candidates and SDP sizes are bounded. A separate cleanup acknowledgment
deadline detects a broken worker port without changing native domain or asset
deadlines. The worker receives an explicitly cloned persisted fingerprint;
it does not install a global storage shim.

Reliable message assembly accumulates bounded immutable fragments and joins once
at completion. The historical SDK recopied all accumulated bytes per packet,
which caused quadratic work for real entity snapshots/assets. This optimization
changes no asset pixels, formats, or quality. A five-pair replay of a real
1.82 MB Hub FBX measured 465.54 ms versus 3.82 ms median assembly time with
identical reconstructed hashes. This is an isolated assembly measurement;
actual world/texture loading results and their limitations are in `STATUS.md`.

A separate test-only `e2e/asset-probe.html` entry constructs the same
`WorkerDirectSession` without a renderer or model loaders. Its serial
ATP fetches retain production admission, service channels, mapping/get packets,
timeouts, SHA-256 checks and the registered tab-local ServiceWorker route. The
driver observes actual versus explicitly requested ATP HTTP fetches and the
actual transferred AssetServer channel; it does not derive transport closure
from a detached main-thread channel handle. Build it separately:
`node node_modules/vite/bin/vite.js build --config e2e/asset-probe-vite.config.ts --outDir ../build/browser-direct/asset-probe-bundle`.
This isolates transport/reassembly timing from scene rendering; it is excluded
from the normal application build and never establishes visual acceptance or a
world-loading improvement.

The historical SDK's missing-packet interval predicate was inverted. After one
lost datagram, its retransmission was treated as a duplicate and the cumulative
ACK could remain permanently before the gap, blocking large ATP replies.
The predicate now matches native `LossList::remove`. Regression tests run actual
reliable PacketLists through the production connection/reassembly code with
loss, reordering, retransmission and 27-bit wraparound, checking exact bytes and
ACK progress. All three failed before the fix and pass afterward. Successful
large-asset/world rendering still requires the independent Chrome runtime check.

Leaving rejects pending asset requests, cancels browser timers, invalidates
generation authority, clears rendering state, sends native disconnect, and
closes signaling/service connections. Native send queues are disposed instead
of retaining retransmission timers after a socket reset. Disposal also fails and
releases unfinished messages in the receive dispatcher. Its address/message
keys use an explicit separator, preventing cross-channel decimal-key collisions.
The domain server binds
signaling to a configurable address/port; laboratory HTTP administration can bind
to loopback with `OVERTE_DOMAIN_SERVER_HTTP_ADDRESS`. Native node UDP sockets
can use `OVERTE_NODE_UDP_ADDRESS`; an empty value preserves `AnyIPv4`, an invalid
IPv4 value fails startup, and a configured interface is retained for reliable
replies, rebinding and the advertised local socket.
With an explicit loopback bind, a verified registered native UDP peer's
same-port loopback reply can activate its observed address when the advertised
address differs. This keeps native reliable handshake/ACK traffic on the same
endpoint. Wildcard binds, nonloopback peers, different ports and RTC behavior
are unchanged.

## Verification status

Production C++ packet-table generation and the current Chrome/native journey
pass. `STATUS.md` records direct admission, entity permissions, actual ATP/HTTPS
content, avatar synchronization, both synthetic audio directions and reconnect,
alongside the controlled loading comparison. Physical bidirectional speech and
hardware navigation remain unqualified. Public direct access to `overte_hub`
requires its real servers to be updated first.
