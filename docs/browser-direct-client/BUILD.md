# Build and self-host the direct browser client

Acceptance is in progress; see [STATUS.md](STATUS.md), [protocol port](SDK_PORT.md),
[transport research](TRANSPORT_RESEARCH.md) and
[renderer provenance](../../browser-direct-client/REUSE.md). Implementation is
materially AI-assisted. The required code and transport components are open.

## Browser distribution

Use Node.js 22.12 or later (CI uses 24) and the versioned lockfile:

```bash
cd browser-direct-client
npm ci
npm run verify:reuse
npm run verify:sdk
npm test
npm run build
```

Serve the complete `dist/` directory over HTTPS, including `asset-worker.js`,
audio worklet, workers/decoders, `default-avatar/` and `THIRD_PARTY_NOTICES.txt`.
Rendering, collision, voice and the tablet execute on the visitor's device.
The static distribution requires no translating service or Node runtime.
Development uses loopback 5187 (`npm run dev`); preview uses 4187. Serve this
version at the site's root: subdirectory deployment, including default-avatar
and decoder routes, has not been qualified. HTTPS or localhost is required for ServiceWorker and
microphone APIs. Capture starts through the visitor's microphone control.

Enter the actual domain's `ws://` or `wss://` signaling URL. An HTTPS page requires
WSS for a remote domain. HTTPS world assets need their origin's CORS permission.
ATP assets use native AssetServer packets over their service DataChannel and
the requesting tab's local ServiceWorker, with generation and SHA-256 checks.
The default local request port connects that ServiceWorker directly to the
owned session worker. It must acknowledge the exact tab/session before native
admission; there is no automatic fallback through the page. Requests are bounded
at 128 per session and 512 across the active ServiceWorker's 64 tab registrations.
Leave revokes native authority and closes outstanding reply ports immediately.
If Chrome ends the idle ServiceWorker context, subsequent asset requests fail
closed; use Reconnect to establish a fresh acknowledged route. A missing old
retirement acknowledgment has a two-second bound and does not prevent that
first reconnect from obtaining its fresh route.
This version supports IPv4 native node advertisements, including null/Any
addresses. IPv6 node advertisements fail with an explicit session error;
deployment on an IPv6-only domain has not been qualified.

## Native server feature

Build the domain server and participating assignment clients from this revision.
Default native builds keep the transport off. Use the normal
[Linux prerequisites](../../BUILD_LINUX.md) and frozen Conan dependencies.
Build [libdatachannel 0.24.6](https://github.com/paullouisageneau/libdatachannel/tree/6b1e2e620f1e37f0eafeee702eaea0043cb305fd)
with its pinned submodules, then supply its installation prefix to Overte:

```bash
cmake -S libdatachannel -B libdatachannel-build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/chosen/prefix \
  -DNO_MEDIA=ON -DNO_WEBSOCKET=ON -DNO_TESTS=ON -DNO_EXAMPLES=ON
cmake --build libdatachannel-build --target install --parallel 4
# Add to the normal Overte configuration:
# -DOVERTE_BROWSER_TRANSPORT=ON -DCMAKE_PREFIX_PATH=/chosen/prefix
```

The exact commit is `6b1e2e620f1e37f0eafeee702eaea0043cb305fd`; its exported
target is `LibDataChannel::LibDataChannel`. Preserve its MPL-2.0/component
notices and corresponding source availability with native deployments. Native
voice retains Overte's 24 kHz PCM packets; native UDP clients retain UDP.
The isolated helper builds these actual source binaries in a digest-pinned
dependency image; instructions and image identity are in [LAB.md](LAB.md).

Enable `webrtc.enable_webrtc`. Configure `webrtc.signaling_address` and
`webrtc.signaling_port` (defaults `0.0.0.0`, 40102). With
`webrtc.enable_webrtc_websocket_ssl`, native WSS reads `overte-cert.key`,
`overte-cert.crt` and `overte-cert-ca.crt` from the domain's app data directory.
The operator may instead terminate TLS with a normal WebSocket-capable reverse
proxy forwarding signaling to the domain. TLS termination does not translate
the domain/entity/avatar/audio protocol.

Normal domain/account authentication, admission and anonymous/group permissions
apply. Browser loopback endpoints receive no native localhost privilege.
Browser qualification currently uses server-authorized guest sessions. A
browser directory/domain account login UI is not qualified in this version;
domains requiring it retain their native refusal behavior. Anonymous joins do
not generate or upload keys to a default directory service.
Rendering projection is read-only and excludes private user data/server scripts;
entity and asset writes remain subject to native permissions and filters.

## ICE and limits

Each responsible server exposes its own DataChannel. Open the chosen UDP ICE
range on those machines and configure the process environment as needed:

| Setting | Meaning |
| --- | --- |
| `OVERTE_BROWSER_ICE_BIND_ADDRESS` | Interface address for ICE candidates |
| `OVERTE_BROWSER_ICE_PORT_MIN`, `OVERTE_BROWSER_ICE_PORT_MAX` | Bounded UDP range |
| `OVERTE_BROWSER_STUN_SERVERS` | Optional semicolon-separated `stun:` URIs; empty by default |
| `OVERTE_DOMAIN_SERVER_HTTP_ADDRESS` | Domain administration bind address, default `0.0.0.0` |
| `OVERTE_NODE_UDP_ADDRESS` | Optional IPv4 bind for native node sockets; empty keeps `0.0.0.0`, invalid values fail startup |

The laboratory uses directly reachable loopback candidates, with no external
STUN. NAT/restricted networks and TURN are not qualified by that result.
Signaling, peers, queues and datagrams are bounded. Entity snapshots have a
16 MiB bound, assets 64 MiB, and asset mappings 4096 entries. Oversized inputs
fail clearly. Native bake mappings resolve before relative model dependencies;
original texture metadata retains the same image quality.

## Checks and acceptance

Protocol generation compiles the actual C++ packet table and datagram limit,
using Qt 6 Core tools and GLM headers:

```bash
python3 browser-direct-client/tools/generate-protocol.py --check
# If GLM is in a prepared Conan prefix, add --include-directory /prefix/include
```

The `Direct browser client` workflow checks generated metadata, immutable reuse,
unit behavior/types/build and the real native servers/transport. Its optional
native ownership is explicit in `.github/native-tests.json`; missing CTest
targets fail and each program is bounded at 45 seconds.
Real browser/native/physical microphone and equal-quality loading evidence
also belong in `STATUS.md`; unit success alone is insufficient. Follow `LAB.md`
for isolated ports, profiles, software displays and process ownership. Downloaded
Hub assets remain ephemeral with provenance; none are redistributed in Git.
The proposed [manual hardware and speech procedure](MANUAL_ACCEPTANCE.md)
describes the remaining human acceptance and its required exclusive resources.
Its commands have not been qualified on hardware.
