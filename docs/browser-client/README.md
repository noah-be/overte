# Overte browser client

The [status](STATUS.md) records implementation and verification progress.
Material implementation assistance: OpenAI Codex.

The browser renders actual Overte entity data locally with Three.js. An open
source, self-hosted gateway runs a separate native Overte Interface connection
for each visitor. Native clients connect to the domain normally. This gateway
uses existing native domain transport and requires reviewed operator-managed
guest settings. It needs no proprietary account or service.

## Components

- Browser: Vite/TypeScript/Three.js, WebGL model and material rendering, walking
  controls and conservative entity-bound collisions, standard avatar visuals,
  and Web Audio capture/playback.
- Gateway: Node.js HTTP/WebSocket service and native bridge script, one isolated
  profile/native process/audio environment per browser connection. The browser
  receives entity snapshots, participant poses and stereo mixed audio; it sends
  its pose, interaction and mono microphone audio.
- Domain: a managed Overte domain and assignment services with a matching native
  protocol and explicit anonymous guest baseline. The actual settings must pass
  the gateway validator before world, avatars or audio are exposed. Public,
  authenticated, IP-restricted and fingerprint-restricted domains are not assumed
  compatible. They require a future identity-preserving server transport.

This approach consumes native-client resources per concurrent visitor. It is a
first-version deployment architecture, not a high-density server design.
The browser still performs the world rendering on the visitor's device.

## Development

Install Node.js 22.12 or newer. From the checkout:

```bash
cd browser-client
npm ci
npx playwright install chromium firefox
npm run build
npm test
npm run test:browser
```

## Reproducible local start

On Fedora x86_64, from the repository root:

```bash
npm --prefix browser-client ci
npm --prefix browser-client run build
python3 browser-client/lab/manage.py prepare
python3 browser-client/lab/manage.py start --gateway --open-browser
```

Open **http://127.0.0.1:8090** and join the offered laboratory domain. The launcher
downloads checksum-pinned native release 2026.04.1 artifacts, creates a separate
real domain and native participant, uploads actual ATP assets and saves verified
guest permissions. It preserves normal user profiles and existing services.
Prerequisites, stop/status commands and asset attribution are in the
[laboratory guide](../../browser-client/lab/README.md).

For development, start the configured gateway in one terminal and `npm run dev`
in another from `browser-client`.
The development browser URL is `http://127.0.0.1:5173`.
The gateway serves production `dist/` directly at `http://127.0.0.1:8090`.
The [gateway guide](../../browser-client/gateway/README.md) provides complete
host dependencies, configuration and the required managed-domain policy.

## Hosting and access boundaries

Use a Linux host with a matching native Overte Interface, a display (an isolated
Xvfb display is suitable), audio transport dependencies and gateway Node runtime.
An administrator explicitly enables domain addresses and HTTP(S) asset origins;
the gateway does not expose an unrestricted arbitrary-address proxy.
`atp:` requests use the connected visitor's native asset client.
HTTPS textures/model dependencies pass through the authenticated same-origin
asset route, subject to the administrator's origin allowlist.

For remote visitors terminate HTTPS at an administrator-managed reverse proxy,
forward WebSocket upgrades and configure the exact public origin. Microphone
access requires HTTPS or localhost. Keep native bridge access on loopback and
set a concurrency limit suitable for native processes on the host.

Each browser receives a session cookie; session assets are tied to that owner.
Native domain admission, asset visibility and entity edit permissions remain
authoritative. Fresh native profiles do not reuse the administrator's account.
The operator must provide a mapping to each domain's actual saved configuration,
using the reviewed settings schema 2.7. Localhost cannot exceed anonymous guest
rights, and privileged guest capabilities are refused. Effective native rights
are checked before session data are released; configuration changes revoke
sessions. Authenticated and source-address/fingerprint policies are refused.
No browser account login or identity-preserving server update is claimed.

Build the production assets with `npm run build`, configure the environment in
the gateway guide, and run `npm start`. Use the supplied
[Nginx example](../../browser-client/deploy/nginx.conf) for HTTPS hosting. The
gateway runs one native Interface and private audio environment per visitor;
choose its session cap according to available CPU and memory.

## Controls

Choose a domain or enter an enabled address, enter your display name and join.
Click the world for mouse look, use WASD/arrows to walk, Space to jump, Shift to
move faster, E to inspect/interact and V for the visible standard avatar view.
Escape releases the mouse. On touch screens the left side controls movement and
the right side controls looking. Enable the microphone explicitly; muting stops
its capture track. Leaving closes the native session and audio resources.

## Verification and supported content

The [verification report](VERIFICATION.md) records real native/browser sessions,
both audio directions and a separate non-fake host capture-device check.
The component suite verifies PCM formats, audio buffering, collision/mapping,
protocol validation and renderer/session behavior in Chromium and Firefox.
Its isolated fixtures are explicitly synthetic. Real-domain acceptance evidence,
including native coexistence and voice, belongs in the laboratory report.

Supported core content includes native primitives, model GLB/glTF/FBX/OBJ/FST
assets, basic material data, textures, text, images and basic lights. FST support
resolves its model filename; FST texture-directory and material mappings and
native `qrc:` resources are not supported. Model
collisions use conservative entity bounds. Advanced particles, procedural
shaders, complete client scripting, tablet tools, VR and full desktop parity are
outside first-version scope; unsupported content is reported to the visitor.

Three.js is MIT licensed; Overte code is Apache-2.0. The production build includes
`THIRD_PARTY_NOTICES.txt` for bundled Three.js and fflate code. Gateway dependencies
retain their licenses in installed packages. The repository's [license guide](../LICENSING.md)
remains authoritative. Do not submit this AI-assisted fork work upstream.
