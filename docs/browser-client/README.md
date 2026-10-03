# Overte browser client

The [status](STATUS.md) records implementation and verification progress.
Material implementation assistance: OpenAI Codex.

Measured optimization work is documented in [model parse tasks](MODEL_PARSE_TASKS.md)
and [passive draw census](ASYNC_DRAW_CENSUS.md). Experimental scheduling remains
disabled by default where the actual Hub comparisons establish no general gain.

The [signed Python runtime guide](SIGNED_PYTHON_RUNTIME.md) explains default
version-2 admission and explicit version-3 package-member authentication for
hosted qualification. Installed-byte and actual isolation gates remain mandatory.

The browser renders actual Overte entity data locally with Three.js. An open
source, self-hosted gateway runs a separate native Overte Interface connection
for each visitor. Native clients connect to the domain normally. This gateway
uses existing native domain transport and requires reviewed operator-managed
guest settings. It needs no proprietary account or service.

## Components

- Browser: Vite/TypeScript/Three.js, WebGL model and material rendering, walking
  controls, actual model-mesh collisions and native avatar rigs,
  and Web Audio capture/playback.
- Gateway: Node.js HTTP/WebSocket service and native bridge script, one isolated
  profile/native process/audio environment per browser connection. The browser
  receives entity snapshots, participant poses and stereo mixed audio; it sends
  its pose, interaction and mono microphone audio.
- Domain: a managed Overte domain and assignment services with a matching native
  protocol and explicit anonymous guest baseline. The actual settings must pass
  the gateway validator before world, avatars or audio are exposed. Explicitly
  configured public places additionally require freshly inspected directory
  settings, compatible protocol and ordinary anonymous guest permissions.
  Authenticated, IP-restricted and fingerprint-restricted domains need a future
  identity-preserving transport; arbitrary public compatibility is not assumed.

This approach consumes native-client resources per concurrent visitor. It is a
first-version deployment architecture, not a high-density server design.
The browser still performs the world rendering on the visitor's device.

## Development

Install Node.js 22.12 or newer and Google Chrome from its official distribution.
Current browser development and qualification use Google Chrome exclusively.
From the checkout:

```bash
cd browser-client
npm ci
npm run build
npm test
npm run test:browser
```

The browser tests select Playwright's installed `chrome` channel. If the official
Chrome executable is outside that channel's standard location, set
`OVERTE_BROWSER_CHROME_EXECUTABLE` to its absolute executable path before
`npm run test:browser`. The launcher refuses invalid paths and has no automatic
fallback to a bundled browser. Historical browser results remain in the status
and evidence reports.

The local `--open-browser` command also uses `OVERTE_BROWSER_CHROME_EXECUTABLE`
when supplied, or the installed `google-chrome-stable`/`google-chrome` executable.
It checks the Google Chrome version before starting laboratory services and
opens Chrome directly, without using the system's default browser.

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
guest permissions. It also prepares version-matched Tablet input modules, a
private native display/network boundary and the explicitly enabled public
`overte_hub` destination. Its actual Chromium rendering/movement/rejoin proof is
linked in [VERIFICATION.md](VERIFICATION.md). Full Tablet behavior and expanded
native feature parity remain under active acceptance testing.
It preserves normal user profiles and existing services.
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
choose its session cap according to available CPU and memory. A deployment
with prebuilt `dist/` assets needs only `npm ci --omit=dev` and `npm start`
from `browser-client`; development dependencies are unnecessary on that host.
The independently installed production deployment and concurrent shutdown were
[verified against the actual domain](VERIFICATION.md#independently-installed-production-deployment-and-concurrent-shutdown).

To produce an auditable self-hosting archive from a reviewed checkout, build the
assets and run `python3 tools/package.py` from `browser-client`. Stage any new
reviewed source modules first; the packager refuses to silently omit untracked
files. It includes runtime sources, compiled assets, documentation, licenses and
`BUILD_INFO.json` with per-file SHA-256 hashes. Candidate archives explicitly
record uncommitted changes. Files changed during packaging and symlinks outside
the regular repository inputs are refused. Output and its checksum are written
under `build/browser-client-distribution` at the repository root.

## Controls

Choose a domain or enter an enabled address, enter your display name and join.
Click the world for mouse look, use WASD/arrows to walk, Space to jump, Shift to
move faster, E to inspect/interact and V for the visible standard avatar view.
Escape releases the mouse. On touch screens the left side controls movement and
the right side controls looking. Enable the microphone explicitly; muting stops
its capture track. Leaving closes the native session and audio resources.
The Tablet button or T opens the genuine installed native Tablet. Its GUI is
relayed from the isolated session; world graphics still render on the visitor's
device. Tablet keyboard/pointer/touch input pauses world input while gravity and
replication continue. Full app-flow acceptance is tracked in the status report.

## Verification and supported content

The [verification report](VERIFICATION.md) records real native/browser sessions,
both audio directions and a separate non-fake host capture-device check.
The component suite verifies PCM formats, audio buffering, collision/mapping,
protocol validation and renderer/session behavior. Current browser journeys run
in Google Chrome; Chromium and Firefox evidence describes earlier checkpoints.
Its isolated fixtures are explicitly synthetic. Real-domain acceptance evidence,
including native coexistence and voice, belongs in the laboratory report.

The Browser client workflow runs its complete checks on matching pull-request
updates. Its former topic-branch push trigger duplicated the same revision's
checks and has been removed. Deduplication preserves every job and check, its
PR path filters, deadlines and permissions. The workflow also defines manual
dispatch.

Supported core content includes native primitives, model GLB/glTF/FBX/OBJ/FST
assets, basic material data, textures, text, images and basic lights. FST support
resolves its model filename and baked material maps; texture metadata resolves
to original browser-supported images. Native baked static FBX/Draco geometry
retains materials and UVs. Six fixed, verified native default-avatar `qrc:`
resources are bundled publicly; other native resource paths are unsupported.
The actual default FBX skins use native named joint poses, model units, hips
registration and native orientation. Skinned baked-model index compatibility
remains under implementation. Loaded models use actual triangle/capsule
collisions; pending geometry has bounded loading protection. Imported model
authoring lights remain metadata, matching native Model behavior, while actual
domain Light entities contribute to scene illumination.

Advanced particles, procedural shaders, full client scripting, remaining Tablet
app behaviors, VR and other native features are mandatory subsequent work under
the user's expanded scope. They are tracked in [FEATURE_PARITY.md](FEATURE_PARITY.md),
with honest implemented and tested states. Unsupported content is reported to
the visitor; the expanded client is not declared complete.

Three.js is MIT licensed; Overte code is Apache-2.0. The production build includes
`THIRD_PARTY_NOTICES.txt` for bundled Three.js, fflate, mesh BVH, GIF and both
official Draco decoder versions. Gateway dependencies
retain their licenses in installed packages. The repository's [license guide](../LICENSING.md)
remains authoritative. Do not submit this AI-assisted fork work upstream.
