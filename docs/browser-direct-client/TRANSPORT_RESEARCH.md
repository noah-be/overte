# Direct browser transport research

Research date: 2026-10-02. Native baseline: fork `main` at
`d569930678`. Material AI assistance: source inspection, implementation and
test design were performed with Codex; runtime evidence is recorded separately.

## Decision

Restore the existing Overte datagram transport with **libdatachannel 0.24.6**,
inside the domain server and each participating assignment client. Use the
native domain, avatar, audio and asset packets after auditing their browser
implementations against this checkout. Add a small authenticated entity JSON
projection to the entity server, using its canonical property serialization.

This choice preserves the native admission and packet-verification paths while
avoiding a second complete implementation of the evolving entity binary
schema. A browser opens a direct DataChannel to each component. The domain
server routes **signaling**, using the existing assignment-client connection;
world, avatar, voice and asset data do not pass through a separate gateway.

| Candidate | Finding | Decision |
| --- | --- | --- |
| Re-enable the historical Google WebRTC code | The current build links audio processing only; its dependency has no peer-connection/DataChannel implementation. The old observer API cannot be enabled by a preprocessor change. | Replace the transport implementation. |
| libdatachannel with native Overte datagrams | Existing `NetworkSocket`, `SocketType::WebRTC`, domain admission and per-node packet authentication can be retained. Browser packet compatibility still needs explicit changes. | Selected. |
| New JSON/WebSocket endpoints for every service | Possible inside the responsible servers, but would require a second admission/session interface and separate avatar/audio/asset service adapters. | Larger compatibility and authorization surface for this version. |
| Unmodified Vircadia Web or Web SDK | Direct connections require DataChannels and an older Vircadia packet dialect. They cannot connect correctly to this Overte baseline unchanged. | Reuse narrowly, with pinned provenance and audited patches. |

## Current primary sources and provenance

These are research snapshots, not evidence that the browser works:

| Project | Inspected source | Version and license |
| --- | --- | --- |
| [Vircadia Web SDK](https://github.com/vircadia/vircadia-web-sdk/tree/35cb07ba5d4a7e06d078d762fcd4584099a26959) | Commit `35cb07ba5d4a7e06d078d762fcd4584099a26959`, committed 2025-12-04 | `2024.1.2`, Apache-2.0, from its [package manifest](https://github.com/vircadia/vircadia-web-sdk/blob/35cb07ba5d4a7e06d078d762fcd4584099a26959/package.json). |
| [Vircadia Web](https://github.com/vircadia/vircadia-web/tree/ff1587fca330d1814d235cfea56935d99ae64533) | Commit `ff1587fca330d1814d235cfea56935d99ae64533`, committed 2025-12-15 | `2024.2.1`; [LICENSE](https://github.com/vircadia/vircadia-web/blob/ff1587fca330d1814d235cfea56935d99ae64533/LICENSE) is Apache-2.0. Its [README](https://github.com/vircadia/vircadia-web/blob/ff1587fca330d1814d235cfea56935d99ae64533/README.md) marks it deprecated in favor of Vircadia World. |
| [libdatachannel](https://github.com/paullouisageneau/libdatachannel/releases/tag/v0.24.6) | Release `v0.24.6`, commit `6b1e2e620f1e37f0eafeee702eaea0043cb305fd`, published 2026-09-26 | MPL-2.0; the [README](https://github.com/paullouisageneau/libdatachannel/blob/v0.24.6/README.md) documents direct Firefox/Chromium interoperability and optional media/WebSocket support. |
| [Vircadia World](https://github.com/vircadia/vircadia-world/tree/9f185373ac89fb5834fda238fa83f51d1d6851a9) | Commit `9f185373ac89fb5834fda238fa83f51d1d6851a9` | A separate service/database architecture in its [manifest](https://github.com/vircadia/vircadia-world/blob/9f185373ac89fb5834fda238fa83f51d1d6851a9/package.json), not a demonstrated native Overte protocol replacement. |

Dependency licenses and source notices must accompany redistribution. The
Overte adapter is Apache-2.0; it does not copy or modify libdatachannel sources.
Its third-party build remains separately pinned and self-hostable. No hosted
account or proprietary service is needed.

## What is actually present in Overte

[WebRTC.h](../../libraries/shared/src/shared/WebRTC.h) defines audio support
on relevant platforms. At the baseline, `WEBRTC_DATA_CHANNELS` was commented
out. [TargetWebRTC.cmake](../../cmake/macros/TargetWebRTC.cmake) links
`webrtc-audio-processing-2` or the Conan audio-processing package. This is echo
cancellation/audio processing, not a browser network transport.

The historical component routes remain behind that feature guard:

- [DomainServer.cpp](../../domain-server/src/DomainServer.cpp):
  `setUpWebRTCSignalingServer`, `routeWebRTCSignalingMessage`, and
  assignment-client signaling dispatch.
- [AssignmentClient.cpp](../../assignment-client/src/AssignmentClient.cpp):
  `handleWebRTCSignalingPacket` and `sendSignalingMessageToUserClient`.
- [NetworkSocket.cpp](../../libraries/networking/src/udt/NetworkSocket.cpp):
  combines UDP and WebRTC datagrams without changing the higher packet layers.
- [NodeConnectionData.cpp](../../domain-server/src/NodeConnectionData.cpp):
  normalizes WebRTC socket addresses to the browser's signaling socket.
- [DomainGatekeeper.cpp](../../domain-server/src/DomainGatekeeper.cpp):
  verifies protocol signature, usernames and connection tokens, optional domain
  OAuth identity, `canConnectToDomain`, bans/permission overrides and capacity
  before creating a verified native node.

The new build flag is `OVERTE_BROWSER_TRANSPORT=ON`; default native builds keep
it off. [TargetDataChannel.cmake](../../cmake/macros/TargetDataChannel.cmake)
requires exactly libdatachannel 0.24.6 and uses its exported
`LibDataChannel::LibDataChannel` target. Existing audio processing and the
qualified Conan dependency graph are unchanged.

## Browser protocol compatibility burden

The pinned SDK's [packet header implementation](https://github.com/vircadia/vircadia-web-sdk/blob/35cb07ba5d4a7e06d078d762fcd4584099a26959/src/domain/networking/udt/PacketHeaders.ts)
has a hard-coded protocol signature
`ad15da90e07d2c7b408325383ad8b77d`. It reports default packet version 22,
EntityData 133, EntityQuery 23 and avatar version 54. This checkout reports
default 23, EntityData 154, EntityQuery 24 and avatar version 55. Changing the
signature alone would claim compatibility with serializers that are different.

Concrete work identified:

1. Generate the browser packet version table/signature from the native
   [PacketHeaders](../../libraries/networking/src/udt/PacketHeaders.cpp), and
   validate the resulting bytes. Keep the native protocol gate enabled.
2. Patch AvatarIdentity serialization: this Overte version has removed the
   attachment count and attachment records. The SDK still writes a four-byte
   zero count and reads that field, shifting subsequent display-name data.
   Compare [native AvatarData](../../libraries/avatars/src/AvatarData.cpp) with
   the [SDK identity packet](https://github.com/vircadia/vircadia-web-sdk/blob/35cb07ba5d4a7e06d078d762fcd4584099a26959/src/domain/networking/packets/AvatarIdentity.ts).
3. Avoid the historical binary EntityData parser. Besides 21 version steps,
   the current native entity enum inserts `ProceduralParticleEffect` at ID 9,
   shifting Line through Material relative to the SDK. New Sound, Canvas,
   Empty and Script types also exist. Property cleanup/reordering means that
   unchanged type IDs alone would not fix binary parsing. Serve canonical,
   permission-filtered JSON from the responsible entity server.
4. If native EntityQuery is used elsewhere, its JSON parameters now use CBOR.
   The SDK's old serializer only supports empty parameters, and the native
   packet version still differs. The browser entity extension avoids this
   parser instead of weakening its version check.
5. Implement native ATP mapping and asset requests. The inspected SDK tree
   contains no `AssetServer` implementation or asset packet serializers;
   a design-document mention is not implemented coverage. A browser-local
   ServiceWorker can expose fetched bytes to model/texture loaders while the
   native asset server retains mapping and session permissions.
6. Audit native domain/socket serialization, UDT message reassembly, HMAC
   placement, avatar traits and audio negotiation with packet fixtures and
   actual server/browser runs. Similar source names do not establish parity.

The packet-buffer ownership audit exposed another compatibility issue:
`LimitedNodeList.sendPacketList` wrote source ID and HMAC into a temporary packet
copy, then sent the original. Once packet clones correctly owned their bytes,
native servers rejected those original reliable messages with local ID zero.
The adapter now fills each queued original before the real UDT SendQueue handles
its handshake and transmission. Incoming sourced packets verify the native
payload HMAC and the current service's WebRTC pseudo port; the native
non-verified, authentication-toggle and domain-server asset-reply exceptions
remain explicit in the generated packet classification tables.

The SDK's [DataChannel implementation](https://github.com/vircadia/vircadia-web-sdk/blob/35cb07ba5d4a7e06d078d762fcd4584099a26959/src/domain/networking/webrtc/WebRTCDataChannel.ts)
creates an unordered channel with zero retransmissions. Native UDT supplies
reliability/ordering for packet types that need it. The restored server adapter
requires that same channel behavior; an ordered/reliable SCTP channel would
add head-of-line delay to audio and movement.

### Payload audit in this implementation

Current native avatar pose flags and record ordering match the selected SDK
schema. The attachment removal affects AvatarIdentity; it does not introduce
a new pose field in AvatarData/BulkAvatarData. Actual production
`AvatarData::toByteArray`, `parseDataFromBuffer`, `packSkeletonData`, and shared
quaternion packing are exercised by
[NativeAvatarAudioWireTests](../../tests/browser-direct-transport/src/NativeAvatarAudioWireTests.cpp)
against the same byte fixtures used by the
[browser tests](../../browser-direct-client/tests/native-avatar-audio.test.ts).

Source inspection identified and corrected payload defects beyond header
versions:

- Joint translation compression now takes the largest **absolute** finite
  component, matching native `AvatarData::toByteArray`; all-negative translations
  previously produced incorrect compressed data.
- Skeleton trait names use UTF-8 byte lengths and byte indexes on write and
  read. Native header/joint sizes remain 11/22 bytes. Joint count, individual
  name length, signed trait length, finite dimensions and zero-dimension
  fallback follow the native bounds. Readers cannot borrow bytes from another
  trait to satisfy a truncated skeleton.
- Six-byte quaternion packing applies native normalization/identity fallback;
  damaged stored components are projected onto the unit sphere during decoding.
- Trait type IDs, int32 versions, int16 body sizes and instanced deletion
  marker `-1` match native `AvatarTraits`. Invalid negative sizes are rejected.
- MixedAudio decoding uses the declared DataView length; backing-buffer padding
  is excluded from PCM. Codec byte lengths are bounded and microphone codec
  names are written as length-prefixed UTF-8.

The adapted SDK still omits avatar-entity/grab trait values, face coefficients,
hand controller transforms and parent/sensor transforms from its public avatar
state; its bulk pose parser consumes their current wire records. This version's
fixtures establish basic unparented pose, scale, identity and skeleton
compatibility. They do not establish complete native avatar feature parity.

## Voice path

The SDK has a real [AudioClient](https://github.com/vircadia/vircadia-web-sdk/blob/35cb07ba5d4a7e06d078d762fcd4584099a26959/src/domain/audio-client/AudioClient.ts)
using microphone input, Web Audio and native mixer packets. It negotiates PCM;
Opus is commented out and no codec implementation is present there. Audio uses
24 kHz, 10 ms frames: 480 bytes of mono or 960 bytes of stereo signed 16-bit PCM
before headers. Both fit the native datagram limit. This allows actual native
audio mixing without a separate media server. Microphone permission,
resampling, output activation and mute behavior still require Chrome tests
under the user's current browser scope; packet or synthetic-tone evidence is
not a real microphone test.

Native microphone PCM payload order is: uint16 sequence; uint32 UTF-8 codec
byte length and codec bytes; uint8 stereo flag; float32 position xyz;
float32 quaternion xyzw; float32 bounding-box corner xyz and scale xyz;
PCM16 bytes. For `pcm`, a mono frame has 542 payload bytes, including 480 audio
bytes. MixedAudio has the same sequence/codec prefix followed directly by
960 stereo PCM bytes. Source:
[AbstractAudioInterface](../../libraries/audio/src/AbstractAudioInterface.cpp),
[AvatarAudioStream](../../assignment-client/src/audio/AvatarAudioStream.cpp),
[PositionalAudioStream](../../libraries/audio/src/PositionalAudioStream.cpp) and
[AudioMixerWorker](../../assignment-client/src/audio/AudioMixerWorker.cpp).
The mixer's existing SilentAudioFrame writes an int32 sample-count constant;
client silent input uses uint16 plus positional data. The fixtures preserve
this existing direction-dependent format.

## Session and resource invariants

- DataChannel establishment does not grant domain admission. Existing native
  protocol signature, identity, permissions and capacity checks remain in use.
- Signaling `from` and opaque session UUID are assigned by the domain server's
  accepted WebSocket. Browser-supplied values are overwritten. Replies must
  match that session, preventing a delayed old reply from reaching a reused
  signaling socket address.
- Only existing user-facing server node types may be signaling targets.
  Internal native signaling must come from the domain/assignment server route.
- Closing the WebSocket emits a close message for every targeted server
  component and a `sessionClosed` event for the admitted native node. Stale
  callbacks compare connection ownership before delivering any datagram.
- RTC close/failure also synchronously removes the matching admitted Agent in
  each native `LimitedNodeList` and purges its UDT queues before an address can
  be reused. Unknown peers, server nodes and active native UDP agents are
  unaffected. No address-only cleanup is queued for a later generation.
- Browser callbacks retain their signaling/session generation and exact peer
  through every asynchronous offer, SDP and ICE operation. Closing clears
  pending startup, ICE and datagrams before notifying the session. A typed
  synchronous `transportDisconnected` signal passes through the browser UDT
  socket to the node list. Old callbacks cannot notify or assign ports to a
  later join; pseudo ports are not reset on leave. Each service creates one
  browser peer, including failed and interrupted startup.
- Library callbacks are marshaled to the owning Qt thread through a destruction
  guard. Native mixer and UDT SendQueue worker writes use synchronized peer
  lookup, channel snapshots and a per-peer send lock.
- Limits: 256 peers/signaling clients per process; 64 remote ICE candidates
  per peer; 64 KiB signaling messages; 48 KiB SDP; 2 KiB ICE candidates;
  128 signaling messages per second per WebSocket; 1 MiB signaling outbound
  buffering. Native datagrams are capped at 1424 bytes.
- RTC-to-Qt callbacks and receive datagrams are bounded to 4096 globally and
  256 per peer; pending receive payloads and socket receive buffering are
  capped at 1 MiB. Buffered outgoing datagrams are capped at 1 MiB per peer.
  Overload drops datagrams; native UDT handles required reliability.
- Browser receive queues use the same 1424-byte MTU, 256-datagram per-service
  bound and 1 MiB combined payload bound. Outgoing browser SCTP buffering is
  capped at 1 MiB per channel; excess writes return failure to native UDT.
- Unresponsive peers expire after 30 seconds. Renegotiation on an existing
  signaling session is rejected; reconnect creates a new session/native node.
- The default ICE configuration has no external STUN/TURN dependency. Operators
  can provide their own STUN URIs through `OVERTE_BROWSER_STUN_SERVERS`
  (semicolon-separated), and choose `OVERTE_BROWSER_ICE_BIND_ADDRESS` plus
  `OVERTE_BROWSER_ICE_PORT_MIN`/`OVERTE_BROWSER_ICE_PORT_MAX`.

Production deployments must supply WSS certificates and reachable ICE ports
for the domain server **and each participating assignment client**. A
representative local domain is the first test target. Public `overte_hub`
direct access requires its actual servers to be upgraded; it cannot be inferred
from a local build or a gateway-backed session.

## Native browser packet admission

The browser endpoint admits the audited Agent protocol through an explicit
allowlist. Native process control, raw entity persistence and raw-file requests
are unavailable on RTC. The domain's corresponding raw-entity handlers also
require native UDP. Browser scene reads use the filtered rendering projection.
The policy runs before normal verification in both the domain server's custom
filter and `LimitedNodeList`; it does not qualify the legacy UDP control plane.

[BrowserPacketPolicy.h](../../libraries/networking/src/BrowserPacketPolicy.h)
permits exactly these browser-to-native packet families; every other packet
type, including newly added native types, is rejected on RTC:

| Family | Allowed packet types |
| --- | --- |
| Domain | `DomainConnectRequest`, `DomainConnectRequestPending`, `DomainListRequest`, `DomainDisconnectRequest`, `DomainServerPathQuery` |
| Peer and avatar | `Ping`, `PingReply`, `AvatarData`, `AvatarIdentity`, `AvatarQuery`, `SetAvatarTraits`, `BulkAvatarTraitsAck`, `RequestsDomainListData` |
| Existing SDK user controls | `NodeIgnoreRequest`, `NodeKickRequest`, `NodeMuteRequest`, `PerAvatarGainSet` |
| PCM voice | `NegotiateAudioFormat`, `MicrophoneAudioNoEcho`, `SilentAudioFrame` |
| Messages | `MessagesData`, `MessagesSubscribe`, `MessagesUnsubscribe` |
| Scene, scripts and ATP | `EntityQuery`, `BrowserEntityQuery`, `EntityScriptCallMethod`, `AssetMappingOperation`, `AssetGet` |

The inventory comes from the adapted SDK's actual packet writers and
`DirectSession`, with native Ping and pending Agent connection compatibility.
The current browser has no `DomainSettingsRequest` writer; wire-declared
assignment-role settings queries remain unavailable. Native UDP behavior and
the packet version/signature table are unchanged. An allowlisted packet still
passes the existing version, identity, HMAC and permission checks; an allowed
moderation or asset operation does not grant moderation or asset-write rights.

[BrowserDatagramValidator.h](../../libraries/networking/src/webrtc/BrowserDatagramValidator.h)
checks RTC frames before queuing them for the native parser. Native UDT reads
its first four bytes and optional 12-byte message header without length checks;
the transport now rejects short frames before those reads. It requires complete
type/version/source/HMAC headers using native packet classifications, accepts
all four native retransmission obfuscation levels, and validates the four
native control types and their sequence-number bodies. Unknown control flags,
unsupported unreliable ordered messages and packet types outside the browser
policy are rejected. Actual local RTC regressions send truncated frames and
then valid native control/reliable packets on the same channel. UDP parsing and
native payload handlers are unchanged; this framing check is not a claim that
every native payload parser has been audited.

Sourced nonverified packets also retain an explicit transport identity check.
The domain's historical private-address fallback is limited to UDP on both
sides. RTC packets require the exact current sender
endpoint, including port and transport. `LimitedNodeList` also requires the
source LocalID to identify the admitted Agent on that RTC channel, using its
active socket or its advertised public/local sockets before activation. These
checks run before nonverified/authentication-disabled exceptions, including in
the audio mixer's `NodeMuteRequest` path; unknown or stale sources cannot borrow
another session's identity.

[LocalUserPolicy.h](../../domain-server/src/LocalUserPolicy.h) keeps native
assignment requests UDP-only before parsing/subnet checks and limits RTC
connect requests to Agent before inspecting pending assignments. Loopback RTC
clients receive the domain's normal guest/authenticated permissions.
[AssignmentMonitorPolicy.h](../../assignment-client/src/AssignmentMonitorPolicy.h)
keeps StopNode and child status restricted to native UDP localhost or the exact
configured monitor interface/endpoint. Matching RTC addresses confer no
process-control privilege. Child status validates its exact 17-byte payload and
returns safely if no child node can be created.

[BrowserEntityProjectionTests](../../tests/browser-direct-transport/src/BrowserEntityProjectionTests.cpp)
exercises the production policies and actual `LimitedNodeList` verifier. Cases
include native control rejection, exact RTC versus wrong port/mixed transport,
unknown/forged nonverified source IDs, authentication toggles, valid and invalid
native HMAC, and preserved UDP private-network behavior. Runtime qualification
is recorded separately; these bounded regressions do not establish complete
native protocol or deployment security.

## Verification scope

[WebRTCTransportTests](../../tests/browser-direct-transport/src/WebRTCTransportTests.cpp)
exercise actual local libdatachannel connections, binary round trips, native
worker-thread writes, stale session closes, queued datagrams after close,
signaling identity/target cleanup, bounded receive queues, and native UDP
coexistence. They need no browser, GPU or persistent domain service.
The lifecycle test also checks admitted-node cleanup and reliable queue removal
while preserving a UDP agent at the same numeric address and port.

[SDK transport lifecycle tests](../../browser-direct-client/tests/sdk-transport-lifecycle.test.ts)
exercise deliberately deferred offer/local/remote SDP completion, stale RTC
and WebSocket callbacks, peer disposal, bounded queues and synchronous failure
propagation. Their reliable-emission test runs the actual SDK SendQueue against
independent native-layout handshake/ACK fixtures, then verifies source ID and
payload HMAC with Node's crypto implementation. Receive tests reject forged
payloads, unknown source IDs and otherwise valid packets on the wrong service
channel, including when authentication is disabled. Native domain-sourced and
domain-server asset exceptions are covered separately. These controlled tests
do not replace the browser/native integration evidence.

The native test target is `browser-direct-transport-WebRTCTransportTests`.
Configure with `OVERTE_BROWSER_TRANSPORT=ON`, tests enabled, and test group
`browser-direct-transport`; then build that target and run its CTest entry.
The CTest timeout is 45 seconds. Build, test and browser/native integration
results belong in [STATUS.md](STATUS.md), with exact commands and limitations.
This research document does not assert runtime completion.

## Browser worker scheduling research

The full-scene Chrome diagnostic shows substantial main-thread long tasks and
delayed native ACKs; the same unchanged assets complete quickly without scene
rendering. Its bounded CPU profile attributes most samples to native program
work outside identified JavaScript; the full-scene result remains negative.

The [current W3C WebRTC specification](https://w3c.github.io/webrtc-pc/#transfering-a-data-channel)
permits RTCDataChannel transfer to a DedicatedWorker in its creation task,
before the first send. RTCPeerConnection remains a Window API. Chrome's
[official implementation and shipping discussion](https://groups.google.com/a/chromium.org/g/blink-dev/c/8CZbYcvQJAY)
records default availability from milestone 130. The actual stock Chrome 153
capability probe passes; these sources and that probe do not qualify a new
application transport path.

The implemented worker now owns DirectSession, NodeList, source/HMAC checks,
UDT sequence/ACK processing and message assembly together. The page retains
RTCPeerConnection control and transfers the real channel immediately in its
creation task. Viewport state, persistent fingerprint and page asset base are
explicit inputs; the ServiceWorker fetch reply MessagePort transfers directly
to the core. Completed validated data crosses to rendering through a bounded,
acknowledged event queue. Leave/rejoin waits for peer retirement and core leave;
AudioWorklet PCM has independent bounded credit and monotonic epochs. Focused
software regressions pass. This implementation still needs actual Chrome/native
scene qualification and equal-quality loading measurements; no performance or
complete user-journey success is inferred from the design.
