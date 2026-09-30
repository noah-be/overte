<!-- SPDX-License-Identifier: Apache-2.0 -->
# Native transport gateway

The browser renders entity and asset data locally with WebGL. A dedicated native
Overte Interface process connects to the domain for each browser session. This
reuses the native UDP transport, entity parsers, avatar protocol, asset client and
audio codecs. It does not stream rendered video. The gateway supports domains
whose actual operator-managed settings pass the anonymous guest policy and whose
native protocol matches the gateway's installed Interface. Other domains,
including authenticated or source-address-restricted domains, need an updated
server transport that preserves browser identity; that transport is not provided
by this first gateway version.

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
a graphical display (a dedicated Xvfb display works), PulseAudio including
`module-null-sink` and `module-native-protocol-unix`, `pactl`, and FFmpeg with Pulse
input/output support. PipeWire on the host can coexist with the private PulseAudio
servers. Each browser session runs its own PulseAudio server containing only two
virtual sinks and a private Unix socket; it cannot access a physical microphone or
speaker through that server. The gateway does not change host audio defaults.

Run `npm ci && npm run build` in `browser-client`, then configure and run:

```bash
export OVERTE_INTERFACE=/absolute/path/to/interface
export OVERTE_GATEWAY_DOMAINS=overte://127.0.0.2:40102
export OVERTE_GATEWAY_ASSET_ORIGINS=https://assets.example.org
export OVERTE_GATEWAY_GUEST_POLICY=/srv/overte/browser-guest-policy.json
node gateway/server.mjs
```

Open `http://127.0.0.1:8090`. When using a release that recognizes only the historical
`hifi:` scheme, additionally set `OVERTE_GATEWAY_NATIVE_SCHEME=hifi`. The browser
continues using canonical `overte:` addresses; only the native launch address is
translated. This does not change or override protocol versions.

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
| `OVERTE_GATEWAY_ORIGINS` | Browser Origin allowlist for WebSocket upgrades; configure the public HTTPS origin behind a proxy. |
| `OVERTE_GATEWAY_HOST`, `OVERTE_GATEWAY_PORT` | Listener address; defaults `127.0.0.1`, `8090`. |
| `OVERTE_GATEWAY_MAX_SESSIONS` | Maximum simultaneous native processes; default 4. |
| `OVERTE_GATEWAY_DISPLAY` | Dedicated display, for example `:94`. |
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
Assets are capped at 32 MiB and requests time out after 30 seconds. Responses
are not cached and recheck active session permission before sending their bytes.
When a domain withholds model URLs, the browser reports that limitation.

Leaving, closing the browser connection, loss of a heartbeat, an audio process
failure or a native process failure tears down the private processes and files.
Leaving first runs the normal native Quit action, which sends avatar/domain
disconnect packets, with a three-second grace period before process termination.
After the quit grace period, any remaining child receives SIGTERM followed by
SIGKILL after three seconds. Teardown awaits process exit before deleting private
files or releasing the session slot; closing sessions still count against the
process limit.
Native bridge startup is limited to 90 seconds and domain connection to 45
seconds. Reconnection creates a new native session rather than reusing stale
authentication state.

## Wire interface

Fetch `/api/session` first to establish the same-origin cookie, then open
`/session`. `/api/config` returns enabled domain choices and audio parameters.
Send `join`, `leave`, `pose`, `mute` and `interact` JSON messages. Receive `state`,
`entities`, `avatars`, initial `pose`, `warning` and `interaction` messages.
Entity properties are native Overte JSON. Quaternion fields are plain numeric
`x`, `y`, `z`, `w` properties. The gateway does not accept array quaternion values.

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
