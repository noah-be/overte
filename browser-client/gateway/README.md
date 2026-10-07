<!-- SPDX-License-Identifier: Apache-2.0 -->
# Native transport gateway

The browser renders entity and asset data locally with WebGL. A dedicated native
Overte Interface process connects to the domain for each browser session. This
reuses the native UDP transport, entity parsers, avatar protocol, asset client and
audio codecs. It does not stream rendered video. The gateway supports managed
domains whose actual operator settings pass the anonymous guest policy, and
explicitly enabled public places resolved through Overte Directory Services.
Both modes require a matching native Interface protocol. Authenticated domains
and access that must preserve the browser's source or machine identity require
an updated server transport; that transport is not provided by this gateway.

The historical `libraries/networking/src/webrtc` implementation is guarded by
`WEBRTC_DATA_CHANNELS`, which is disabled in `libraries/shared/src/shared/WebRTC.h`.
Audio processing using WebRTC does not provide a browser transport. The
[Vircadia Web SDK](https://github.com/vircadia/vircadia-web-sdk) and
[Vircadia Web](https://github.com/vircadia/vircadia-web) implement browser clients,
but require their corresponding native WebRTC data-channel transport and protocol
versions. Neither compatibility nor a safe protocol-version override was assumed.
The native gateway deliberately avoids changing native protocol validation.

## Host dependencies

Use Linux with Node 22.12 or newer, a matching native Overte Interface executable,
Bubblewrap and `unshare` with unprivileged user/PID/network namespaces, Python 3,
iproute2 (`ip`), slirp4netns with `--disable-host-loopback` support, Xvfb, xauth, PulseAudio including
`module-null-sink` and `module-native-protocol-unix`, `pactl`, and FFmpeg with Pulse
input/output support. PipeWire on the host can coexist with the private PulseAudio
servers. Each browser session runs its own PulseAudio server containing only two
virtual sinks and a private Unix socket; it cannot access a physical microphone or
speaker through that server. The gateway does not change host audio defaults.
Each session also receives its own authenticated Xvfb display. A shared operator
desktop is not used by native workers. The genuine Tablet input helper requires
the QtQuickTest `TestEvent` module and its libraries from the same Qt ABI as the
selected native package; a mismatched system Qt module is not interchangeable.
The small [native input extension](../native-input/README.md) additionally preserves
composition, literal text, validators, selection and undo. For the reviewed Qt 5.15
worker, build it with `python3 tools/build-native-input.py --qt-libraries /absolute/path/to/native/usr/lib`
from `browser-client`, and add the printed generated module's parent `qml` directory
to `QML2_IMPORT_PATH` alongside the matching QtQuickTest imports. Its pinned SDK
requires `g++`, `ar` and `tar`; it does not install or replace a Qt runtime.

Run `npm ci && npm run build` in `browser-client`, then configure and run:

```bash
export OVERTE_INTERFACE=/absolute/path/to/interface
export OVERTE_GATEWAY_DOMAINS=overte://127.0.0.2:40102
export OVERTE_GATEWAY_ASSET_ORIGINS=https://assets.example.org
export OVERTE_GATEWAY_GUEST_POLICY=/srv/overte/browser-guest-policy.json
export OVERTE_GATEWAY_MANAGED_UDP_PORTS=40102,45200,45201,45202,45203,45204,45205
node gateway/server.mjs
```

Enable the actual native Tablet by setting `OVERTE_GATEWAY_DEFAULT_SCRIPTS` to
the installed `scripts/defaultScripts.js` and supplying the matching Qt import
paths described above. Add `https://content.overte.org` to the **managed** asset
origin list when using the packaged native avatar favorites such as Kim. Public
asset origins remain separate. An unapproved model source reports the explicit
gateway refusal and does not silently broaden that list.

Open `http://127.0.0.1:8090`. When using a release that recognizes only the historical
`hifi:` scheme, additionally set `OVERTE_GATEWAY_NATIVE_SCHEME=hifi`. The browser
continues using canonical `overte:` addresses; only the native launch address is
translated. This does not change or override protocol versions.

The UDP example assumes the operator configured the domain on port 40102 and
its six assignment clients on fixed ports 45200–45205, for example with
`assignment-client --min-listen-port 45200 -n 6`. Supply the actual fixed ports of
your domain and mixers, not a broad port range. The laboratory uses domain port
45102 instead. Missing scope, non-loopback managed domains, and a list omitting
the domain server port are rejected. Public mode uses its separately validated
Directory Services destination and does not require a managed UDP relay list.

Native Interface historically replaces domain ports for `127.0.0.1` with a
process-global shared-memory port, even when the URL has an explicit port. That
can redirect a native connection to another local domain. The gateway resolves
and pins the native IP before launch and rejects `127.0.0.1`; use a dedicated
loopback address such as `127.0.0.2` for the domain. The isolated laboratory and
denied-domain fixture use isolated IPC namespaces to preserve their intended
network destinations. The browser's selected hostname still identifies its
reviewed configuration; native permission reports must match the pinned address.

Configuration variables:

| Variable | Purpose |
| --- | --- |
| `OVERTE_GATEWAY_DOMAINS` | Comma-separated exact domain address allowlist; default is local port 40102. |
| `OVERTE_GATEWAY_ASSET_ORIGINS` | Comma-separated exact HTTPS/HTTP asset origins, including permitted redirect destinations; default empty. |
| `OVERTE_GATEWAY_GUEST_POLICY` | Required absolute path to the reviewed mapping of each domain to its actual operator-managed domain settings file. |
| `OVERTE_GATEWAY_PUBLIC_PLACES` | Optional comma-separated lowercase Directory Services place-name allowlist; empty by default. |
| `OVERTE_GATEWAY_PUBLIC_INTERFACE` | Optional matching native executable or administrator-owned wrapper for public places; defaults to `OVERTE_INTERFACE`. |
| `OVERTE_GATEWAY_PUBLIC_INTERFACE_LIBRARY_PATH` | Optional public-native library path, separate from the managed worker version. |
| `OVERTE_GATEWAY_PUBLIC_ASSET_ORIGINS` | Separate exact origin allowlist for public-world assets and redirects; empty by default. Public worlds cannot use the managed asset-origin list. |
| `OVERTE_GATEWAY_DEFAULT_SCRIPTS`, `OVERTE_GATEWAY_PUBLIC_DEFAULT_SCRIPTS` | Actual version-matched installed `scripts/defaultScripts.js` file URL or absolute path; the public worker may use its own version. Enables its genuine system Tablet and packaged applications. |
| `OVERTE_GATEWAY_ORIGINS` | Browser Origin allowlist for WebSocket upgrades; configure the public HTTPS origin behind a proxy. |
| `OVERTE_GATEWAY_HOST`, `OVERTE_GATEWAY_PORT` | Listener address; defaults `127.0.0.1`, `8090`. |
| `OVERTE_GATEWAY_MAX_SESSIONS` | Maximum simultaneous native processes; default 4. |
| `OVERTE_GATEWAY_XVFB`, `OVERTE_GATEWAY_BWRAP` | Trusted Xvfb/Bubblewrap executable paths; defaults `Xvfb` and `bwrap`. Each native session gets a separate display. |
| `OVERTE_GATEWAY_SLIRP` | Trusted slirp4netns executable; default `slirp4netns`. Required for isolated public and managed workers. |
| `OVERTE_GATEWAY_MANAGED_UDP_PORTS` | Required exact comma-separated domain and assignment UDP ports for managed isolated workers, maximum 32 distinct ports. The domain must use a dedicated loopback IPv4 address. |
| `OVERTE_GATEWAY_NATIVE_ROOT`, `OVERTE_GATEWAY_PUBLIC_NATIVE_ROOT` | Reviewed installed package root, mounted read-only inside the corresponding worker. AppRun defaults to its package directory; unpackaged builds should specify their complete prepared runtime root. |
| `OVERTE_INTERFACE_LIBRARY_PATH` | Library path for an unpackaged native executable. |
| `OVERTE_GATEWAY_PULSEAUDIO` | PulseAudio executable or host-specific wrapper; default `pulseaudio`. |
| `OVERTE_GATEWAY_PULSEAUDIO_MODULES` | Optional module search directory for an unpackaged PulseAudio installation. |
| `OVERTE_GATEWAY_PULSEAUDIO_LIBRARY_PATH` | Optional private daemon library path. |
| `OVERTE_GATEWAY_RADIUS` | Entity query radius in metres; default 512. |

Expose the gateway through an HTTPS reverse proxy with WebSocket upgrade support
for `/session`, forward the original HTTPS scheme, and configure the exact public
Origin. Browser microphone access requires HTTPS or localhost. Do not expose the
native bridge route `/native` through a proxy; it is local-only and authenticates
with an independent per-session secret. No proprietary services or accounts are
required for anonymous-capable domains.

## Permissions and lifecycle

Each native process has a fresh private XDG configuration, data and cache
directory. It starts muted and does not inherit the gateway operator's saved
accounts or credentials. Domains retain normal anonymous visitor connection,
asset visibility and entity edit permissions. Account-required domains refuse
these anonymous sessions; the refusal is shown in the browser. Authenticated
domain login in the browser is a remaining limitation, not a permission bypass.

Workers run inside a filesystem, user, PID and IPC namespace. Only the reviewed
native package/Qt runtime roots, system libraries/fonts/TLS trust files, the
session's writable profile and that session's authenticated X socket are
mounted. Operator home directories, other sessions, host X authority, SSH
sockets and host process environments are unavailable. The native environment
is cleared before explicit runtime/audio settings are supplied; FFmpeg uses a
separate host environment so bundled native Qt/OpenSSL libraries cannot replace
its system libraries. A fresh session-local machine ID prevents inheriting the
operator's fingerprint. Ending the namespace removes native subprocesses,
including children that ignore SIGTERM. Display ownership is released only
after teardown finishes.

The native worker additionally runs in a private network namespace. A trusted
outer owner configures slirp with host-loopback access disabled and prohibits
private, reserved and metadata network routes. The inner worker cannot change
the outer routing policy. A bounded Unix relay exposes only this session's
authenticated native WebSocket upgrade. Managed local domains use a second
scoped relay for their explicit UDP ports; it preserves real replies and exposes
no unspecified host UDP service. Public native UDP uses normal public network
egress. No shared operator D-Bus or desktop clipboard is exposed.
Public places and Tablet applications require worker isolation.
`OVERTE_GATEWAY_WORKER_ISOLATION=off`
exists only for trusted managed transport diagnostics without Tablet apps; it
is refused for public or Tablet sessions.

Domain permissions that depend on the UDP source address see the gateway host,
because it is the native network participant. Administrators must authorize that
host as a browser visitor with appropriate permissions. In particular, a gateway
on the same machine as a domain can match the domain's `localhost` permission
rule. Do not enable such a domain for untrusted visitors while that rule grants
trusted operator access. The domain allowlist is an explicit administrator
decision, and does not reproduce the original browser's source address.

The gateway therefore requires an actual settings mapping:

```json
{
  "version": 1,
  "mode": "anonymous-baseline",
  "domains": [
    {
      "domain": "overte://127.0.0.2:40102",
      "settingsFile": "/srv/overte/domain-user-config.json"
    }
  ]
}
```

The settings file must be the operator-managed actual configuration, with the
reviewed settings schema version `2.7`. A copied or guessed configuration does
not prove a remote domain's policy. The validator requires explicit booleans for
all 11 known permissions in the anonymous and localhost rows, anonymous connect
and asset URL viewing, and no localhost privileges beyond the anonymous baseline.
Guest administration, asset writes, lock adjustment, content replacement, private
user data access, kicking and capacity bypass are rejected. Source IP/fingerprint
overrides, OAuth and legacy restricted-access rules are also rejected.

The native bridge reports its effective exposed permissions before releasing
connected state, entity data, avatar data or PCM audio. They must match the
validated guest policy. Domain authority changes revoke that approval and mute
native input; revision-correlated acknowledgments prevent an old approval from
authorizing a new domain. Actual configuration files are checked again every 10
seconds, and changes or invalid policy bindings revoke active sessions. Capacity
bypass has no scripting getter in the tested native release, so its prohibition
is checked in the actual operator-managed configuration. This is an explicit
managed-domain deployment boundary, not cryptographic attestation of arbitrary
remote server configuration.

## Public places

Public mode is an independent anonymous native visitor. It neither requires nor
fabricates an operator settings file for a public domain. Enable only reviewed
place names, for example `OVERTE_GATEWAY_PUBLIC_PLACES=overte_hub`. The browser
then offers `overte://overte_hub`. The gateway uses the native client's anonymous
`https://mv.overte.org/server/api/v1/places/<name>` endpoint, requires an active,
open place with unlimited capacity, and pins its advertised public IPv4 address,
UDP port and spawn path. Private, loopback, reserved and DNS-based advertised
destinations are rejected. Directory requests use a fixed HTTPS authority,
disallow redirects, and have a 15-second timeout and 1 MiB response limit.

Before joining, the actual selected executable writes its native protocol
signature with `--protocolVersion`; it must exactly match the directory's
advertised signature. Native protocol validation also remains enabled during
the real handshake. The inspection process belongs to the session, times out
after 20 seconds, and is terminated with the same bounded TERM/KILL cleanup when
the visitor leaves. A separate `OVERTE_GATEWAY_PUBLIC_INTERFACE` allows a newer
public-domain worker alongside the older matching managed laboratory client.
For an unpackaged development tree, `lab/public-interface.sh` supplies its Qt
paths and explicit Desktop display selection; configure
`OVERTE_PUBLIC_NATIVE_ROOT` to that prepared installation.

The bridge must report all ten script-exposed effective permissions and the
exact pinned authority before data or audio are released. Connection and asset
URL visibility are required. Lock adjustment, content replacement, private user
data and kicking are rejected. Ordinary anonymous rez and asset-upload rights
granted by the public server are retained; the gateway has no generic asset-write
endpoint. Capacity bypass has no native scripting getter, so public mode only
accepts unlimited-capacity places and does not invent an observed capacity flag.
The native `location.href` is a shareable display address and may change from
the pinned IP to the configured place name after lookup. Approval additionally
requires the actual native `location.domainID` to match the directory's domain
UUID. Only the pinned authority and that configured canonical alias are accepted;
changes of actual domain identity always require fresh permission approval.
Every 30 seconds the directory availability, capacity, destination and protocol
are checked again; an unavailable or changed record revokes the connection.

The public server sees the gateway's UDP source address and the isolated native
worker's machine fingerprint, not the browser's original identity. The fresh
session machine ID also avoids copying the operator's machine identity. The browser receives this deployment
warning. Public mode cannot establish that a remote server's unexposed policy
matches an operator-managed baseline, or preserve source-IP/fingerprint access
restrictions. Native authentication failures remain enforced. This opt-in mode
does not promise compatibility with arbitrary public domains. Configure
`OVERTE_GATEWAY_PUBLIC_ASSET_ORIGINS` from the reviewed world's actual origins;
unknown and unapproved redirect origins remain denied.

Asset reads use an HttpOnly SameSite session cookie and the owning active native
session. `atp:` requests pass through that session's native asset client. HTTP and
HTTPS requests, including redirects, are limited to administrator-approved
origins. Each outgoing URL is rebuilt from the selected configured origin;
world-provided URLs contribute only the resource path and query. Credentials,
alternate schemes and unapproved redirect authorities are rejected before fetch.
The origin allowlist permits every resource path on each listed server; configure
asset-serving origins whose readable content may be exposed to domain visitors.
Asset responses carry a Content Security Policy sandbox so HTML/SVG
navigations cannot execute scripts with the gateway origin or credentials.
Assets are capped at 32 MiB and readers time out after 30 seconds, including
queue time. Sixteen upstream downloads run concurrently; up to 128 distinct URLs
and 512 readers can wait. Duplicate readers share one upstream request. The last
HTTP reader's cancellation aborts that download. Native ATP work retains its
concurrency slot until its real callback or native 30-second deadline, because
that scripting API cannot cancel an active asset request.

Each visitor session keeps an in-memory LRU byte cache of at most 128 MiB and
256 entries for 30 seconds. This reduces repeated texture/model downloads while
allowing mutable paths to refresh; it is not a persistent or shared account
cache. The configured session limit therefore also controls aggregate retained
cache memory (four sessions can retain 512 MiB), in addition to active download
buffers. Cache entries and pending readers are invalidated on permission revision,
domain reconnect and leave. Every hit still checks cookie ownership, the actual
origin allowlist and current native permission revision. HTTP responses remain
`private, no-store` and sandboxed so browser caching cannot bypass those checks.
The response includes its bounded byte length and `x-overte-asset-source`
(`download`, `shared` or `memory`) for measuring this visitor's transfer reuse;
these headers contain no source URLs, credentials or other visitor state.
When a domain withholds model URLs, the browser reports that limitation.

Leaving, closing the browser connection, loss of a heartbeat, an audio process
failure or a native process failure tears down the private processes and files.
Leaving first runs the normal native Quit action, which sends avatar/domain
disconnect packets, with a three-second grace period before process termination.
After the quit grace period, any remaining child receives SIGTERM followed by
SIGKILL after three seconds. Teardown awaits process exit before deleting private
files or releasing the session slot; closing sessions still count against the
process limit. Concurrent leave, socket-loss and gateway-shutdown requests share
the same cleanup promise, so shutdown also waits for an already-closing session.
Shutdown rejects new HTTP requests, WebSocket upgrades and joins before draining
sessions, while retaining existing native bridges for the normal Quit action.
Obsolete join failures and leave notices cannot reset a replacement session.
Native bridge startup is limited to 90 seconds and domain connection to 45
seconds. Reconnection creates a new native session rather than reusing stale
authentication state.

The native bridge and trusted Tablet helper sources belong to the running gateway
version. Restart the gateway after protocol/source changes during development;
deploy immutable complete build artifacts so browser, gateway and native helper
versions stay coherent throughout every session.

## Wire interface

Fetch `/api/session` first to establish the same-origin cookie, then open
`/session`. `/api/config` returns enabled domain choices and audio parameters.
Send `join`, `leave`, `pose`, `mute` and `interact` JSON messages. Receive `state`,
`entities`, `entityUpdates`, `avatars`, initial `pose`, `warning` and `interaction` messages.
Entity properties are native Overte JSON. Quaternion fields are plain numeric
`x`, `y`, `z`, `w` properties. The gateway does not accept array quaternion values.
Browser frames are limited to 192 KiB so a 64 KiB UTF-8 clipboard still fits after
JSON escaping; each command also retains its own validation and size limits.
Each approved connection begins with a full `entities` snapshot. Subsequent
`entityUpdates` messages contain complete changed entity properties and a
`removed` array of identifiers. Aging and render-diagnostic fields are ignored
only when comparing entities; changed records retain their native properties.
Reconnection always starts with a fresh snapshot. A slow connection whose world
updates exceed the bounded socket queue is closed rather than silently losing
incremental state.

Native Tablet navigation within the approved domain emits `poseRequest` with a
canonical UUID `nonce`, the current `permissionRevision`, and the actual native
position/orientation. The browser applies that spawn and echoes `poseAccepted`
with the same nonce and revision. Old browser poses are paused until that exact
acknowledgement; a newer native teleport supersedes the previous nonce. No
acknowledgement within 15 seconds produces a clear connection error and cleanup.
Domain changes continue through the ordinary domain permission/admission gate.

Genuine native Tablet frames and inputs use revision-bound `tablet` messages.
The native worker's opaque/transparent 3D draw jobs are disabled while retaining
its Tablet/HUD UI; browser world rendering remains local. Snapshot adapts only
the installed application's capture call to the browser's actual scene, retaining
the native app and review callbacks. Its generated script is mounted read-only
at the original installed path without editing the host package.
`/api/tablet-files/<sessionId>` provides cookie-owned visitor file inventory,
upload, download and deletion. Mutations require an allowed browser Origin.
The descriptor-bound workspace accepts plain names, limits files to 64 MiB,
total uploads to 256 MiB and inventory to 256 files, with at most 16 concurrent
operations/streams. Downloads are inert attachments and never follow native
symlinks into host files. Native file dialogs can access only the session's
mounted workspace/runtime, never an operator home directory.

Binary browser input is signed 16-bit little-endian mono PCM at 48 kHz. Binary
output is signed 16-bit little-endian stereo PCM at 48 kHz, always aligned to
complete four-byte stereo frames. Queues are bounded and drop late audio rather
than accumulating delay. The native client spatializes and encodes/decodes audio
through the domain's real audio mixer.

Run the dependency-light transport checks with:

```bash
node --test gateway/*.test.mjs
```

These checks verify validation, Origin and cookie boundaries, native secret
authentication, asset session ownership and recovery from denied launches. They
are separate from actual domain/browser/native functional integration tests.
The user explicitly cancelled the proposed 30-minute endurance test.

After preparing the isolated laboratory, the actual native server refusal path
can be tested with `node tests/native-denial.mjs`. It starts a separate domain on
`hifi://127.0.0.1:45302` and HTTP 45300 in a private user/IPC namespace, denies anonymous and localhost connection permissions,
and verifies the native bridge reports the server refusal without exposing world
data. Its HTTP administration requires an ephemeral random credential kept only
in private runtime files. It stops its own processes and writes
`test-results/native-denial.json`. This check requires `unshare` and enabled user
namespaces; its private domain and native client share their own IPC namespace,
so native automatic port discovery cannot affect another local domain.

Native transport liveness uses a fresh, random `nativePing`/`nativePong` application challenge with a strict 30-second response deadline. Ordinary native heartbeats and unrelated packets do not acknowledge it. This proves delivery to the native script engine and its response; Qt control Pong proved unreliable during the real Hub tests. Browser connections retain standard WebSocket Ping/Pong checks. Rejected duplicate native connections never acquire ownership of an existing session cleanup.

After its initial authenticated handshake, the native bridge queues socket output for its existing 50 ms Script timer. Every deferred world, avatar, pose, asset and Tablet message captures the approved revision and authority and is checked again before transmission. The queue coalesces only replaceable avatar/heartbeat messages and fails closed at 128 messages or 64 MiB of UTF-8 output; it never silently drops entity updates. Native challenge responses have a separate exact nonce and expiry and take priority. Entity acquisition yields every 8 ms or 64 records, resumes after 16 ms, and publishes complete ordered snapshots/deltas without overlapping scans.

A rapid rejoin may display “Waiting for your previous connection to close…” while the same browser owner’s already-closing worker completes native quit and process cleanup. The old worker retains its capacity slot until cleanup finishes. The new admission checks capacity again before allocating resources; foreign active or closing sessions do not qualify for this wait. Leave, socket closure and shutdown cancel pending admission.

The visitor WebSocket envelope remains 192 KiB. Clipboard text allows tabs/newlines/carriage returns and quotation escaping within its 64 KiB UTF-8 limit; unsupported C0/NUL/DEL controls are refused independently of framing.

The installed Places app is adapted at three reviewed navigation entry points before native location lookup: destination/Home and browser history. Exact version-matched Places JavaScript and UI files are mounted read-only inside the worker; the operator's installation is preserved. Destinations are admitted against configured managed authorities or freshly resolved configured Directory Services places. Only finite bounded positions and normalized orientations survive viewpoint paths. Unsupported targets produce a clear warning while the current approved session remains connected. Approved navigation revokes the old session before the browser starts fresh admission; Back/Forward use bounded browser history and never reuse another domain's native profile or permissions.

Avatar packets contain the real native skeleton URL, skeleton offset and matching bulk joint names, rotations and model-unit translations. The bridge samples the complete rig at most every 100 ms and includes matching arrays in its 20 Hz participant snapshots. It refreshes names with each bulk sample because model loading is asynchronous; unsupported or invalid rig data is represented by empty matching arrays rather than an invented pose. Native resource access remains limited to the verified default-avatar browser bundle.

Places wire messages are `{type:"navigation",nonce,permissionRevision,domain}` and `{type:"navigationHistory",nonce,permissionRevision,direction:"back"|"forward"}`. The nonce is a canonical lowercase UUID and the revision must match the currently approved session. Connected state includes `permissionRevision`; browsers return `{type:"navigationHistoryState",permissionRevision,canGoBack,canGoForward}` with booleans to update the real native Places controls. Avatar joint arrays contain at most 1,000 records; names are nonempty and bounded to 128 characters, rotations are finite normalized quaternions, translations retain native model units, and skeleton offsets are finite bounded vectors. The self avatar is sent once with its actual session UUID, excluding AvatarManager's null-key alias.

Places Bookmarks and Home are visitor preferences stored in the browser's own origin-local storage. A shared browser/gateway validator accepts at most 100 unique plain bookmark names (64 UTF-16 characters and 256 UTF-8 bytes), safe Overte addresses of at most 1,024 characters, and an optional Home. Account data, credentials, queries, fragments, file/asset/HTTP URLs and malformed viewpoints are refused. Safe unlisted destinations may remain saved, but clicking them still passes through ordinary configured domain admission and displays a refusal without redirecting the current worker. The native adapter restores only LocationBookmarks values after actual permission approval, using the packaged application's legacy domain scheme internally. No Qt settings or account profile crosses worlds. The native reserved Home bookmark maps to the explicit Home field.

Actual preference changes carry `{type:"visitorPreferences",permissionRevision,bookmarks,home?}` and are accepted only for the connected approved revision. A new `join` may contain a validated `visitorPreferences` object. The installed Places adapter reports Add/Delete/Rename/Home changes immediately and flushes saved values before navigation; bounded one-second polling also catches changes through other native bookmark controls. Visitor preference persistence never changes domain rights or bypasses fresh destination validation.

A visitor without a saved Home receives no empty native Home bookmark. Ordinary unsupported addresses typed into Places, including file/HTTP URLs and an empty target, produce an admission warning while preserving the authenticated current session. Invalid transport metadata, forged nonces and stale approval revisions still fail closed.

With the private managed/public laboratory configured, `node tests/integration/tablet-places.mjs` starts an owned gateway on port 8093 and exercises genuine installed Places controls: finite address navigation, Bookmark/Home creation and restoration, Back/Forward, an actual freshly resolved Hub IP/port/viewpoint, and Home back to the managed domain. It compares actual native avatar positions and session changes. Public audio, entity edits and asset uploads remain disabled during this read-only journey. The ignored runtime report and PNGs are under `build/browser-hub-lab/places-proof`; only sanitized aggregates should be published.
The harness owns an explicit browser child process and records its exit/crash events and bounded private diagnostics; cleanup never selects other browser processes.

Visitor persona persistence uses a separate, browser-owned DTO. A `join` packet may include `visitorPersona` with optional `displayName`, `avatarURL`, `avatarScale` and `avatarFavorites`. Names allow 256 UTF-16 code units and 1 KiB UTF-8; native target scale is bounded to 0.005–1000. Favorites are `{name, avatarURL, avatarScale, avatarIcon?, avatarEntities?}` records, with at most 100 unique names and 32 supported Model wearables per favorite. The complete normalized persona must fit 48 KiB; the existing 192 KiB browser WebSocket envelope remains unchanged. Favorites use a reviewed property allowlist: transforms, model/textures, joint parenting, visibility/material basics and ordinary collision/grab properties. Scripts, account values, arbitrary paths and unreviewed entity properties are refused. Unsupported native collections produce a warning and omit that field, preserving the previous saved browser collection; an explicit empty array deletes it.

HTTP avatar and wearable addresses must use the session's configured asset origins. ATP uses the current domain asset service. Resource/QRC addresses are limited to the exact packaged default avatar FST and mannequin FBX, including equivalent leading-slash forms; this is not a general native resource or file proxy. A remembered asset origin unavailable in the destination domain is warned about and left in browser storage. Its replacement default is not silently persisted before the visitor makes an explicit native change.

The gateway writes only validated version-3 avatar favorite records to the fresh worker's private `data/Overte/Interface/avatarbookmarks.json` before Interface starts. The native file's existing `avatarUrl` and `avatarEntites` spelling is confined to that adapter. No Qt profile, account, operator file or session UUID is imported. Set `OVERTE_GATEWAY_NATIVE_ORGANIZATION` / `OVERTE_GATEWAY_PUBLIC_NATIVE_ORGANIZATION` to the matching reviewed `Overte`, `Overte - Dev`, `Overte - Nightly` or `Overte - PR<number>` organization when using a different build flavor. Actual MyAvatar display name/model/scale restoration waits for approved permissions; native changes return `{type:'visitorPersona', permissionRevision, ...presentFields}` under the same revision and engine outbox guards as world/UI data. The documented single-entry bookmark getter recovers the native QVariant-to-JS map's `__proto__` name conversion loss without banning legitimate favorite names.

`node tests/integration/visitor-persona.mjs` verifies this adapter against two fresh real native workers and the isolated managed domain. It checks native API favorite records, a full Unicode display name, the actual packaged avatar and user scale; it does not substitute for the separate genuine People/Avatar app journey. During teardown, Interface exits while its private display and PulseAudio remain available. Other media/display children stop afterward and PulseAudio stops last, with the existing process termination bounds.
