# Real Overte acceptance laboratory

This laboratory runs an actual Overte domain server, six assignment processes,
a separate native Interface participant, and the browser gateway. The browser
renders downloaded entity and asset data locally. There is no simulated server
or built-in browser demo scene.

## Reproduce on Fedora x86_64

Prerequisites: Fedora with `dnf download`, Python 3.11+, Node.js 22.12+, npm,
`rpm2cpio`, `cpio`, `ar`, `tar` with zstd support, `bubblewrap` (`bwrap`),
`xauth`, `g++`, `iproute` (`ip`), `unshare` with unprivileged user/network/IPC
namespaces, FFmpeg with PulseAudio and X11 support, and `pactl`.
The bootstrap downloads and extracts Xvfb, PulseAudio, matching pinned Qt 5.15.3
Tablet input modules and the official Fedora `slirp4netns` package locally. It
does not install system services or change the desktop's PipeWire setup. A small
QML input extension is compiled against pinned official Qt 5.15.3 headers and
the existing native runtime, preserving native composition, validators and undo.

Run from the repository root:

```bash
npm --prefix browser-client ci
npm --prefix browser-client run build
python3 browser-client/lab/manage.py prepare
python3 browser-client/lab/manage.py start --gateway --open-browser
```

Open **http://127.0.0.1:8090** and join the offered laboratory domain. The native
domain is `hifi://127.0.0.2:45102`; current browser input also accepts its
`overte://127.0.0.2:45102` spelling. The pinned 2026.04.1 native release uses the
historical `hifi:` scheme. The loopback alias `127.0.0.2` deliberately avoids
that release's special `127.0.0.1` shared-memory domain-port auto-discovery,
which would otherwise mix independent test domains. The domain server additionally
runs in its own unprivileged user and IPC namespace, so its Qt shared-memory
port announcement cannot overwrite another local domain's discovery slot. The domain administration port is 45100; the fixture
HTTP server listens only on loopback at 45110. Xvfb displays :94 and :95 are
reserved for laboratory infrastructure and the independent native participant
respectively. Each browser visitor receives a separate authenticated Xvfb
display, private process/filesystem namespaces and its own restricted network
namespace. Public worker networking cannot reach host loopback or private
networks; managed UDP forwarding admits only the explicitly configured lab
domain/mixer endpoints.

The exact release artifacts and SHA-256 checksums are pinned in `manage.py`;
prepared artifact identities, including downloaded Fedora packages, are recorded
in `build/browser-lab/evidence/artifacts.json`. A cached AppImage can be supplied
with `prepare --client-artifact /absolute/path/Overte.AppImage`; its checksum must
still match. Other hosts can use the gateway's documented native dependencies,
but this automatic acceptance bootstrap is specifically tested on Fedora x86_64.

All runtime profiles, processes, logs, commands and test recordings remain under
the ignored `build/browser-lab` directory. The launcher refuses occupied ports
and displays, and verifies recorded PID identities before stopping its own
process groups.

```bash
python3 browser-client/lab/manage.py status
python3 browser-client/lab/manage.py restart-gateway
python3 browser-client/lab/manage.py stop
```

The launcher first provisions the actual scene and ATP asset using a temporary
local native author. It then saves and reads back a minimal identical permission
baseline for anonymous users and localhost: connect, rez/edit entities, avatar
entities and visible asset URLs. The fixture's color interaction uses the normal
entity edit permission; guests on other domains may instead use world-authored
pointer/script interactions. Asset writes, domain administration and privileged content
operations are disabled before the gateway starts. The gateway validates both
the managed settings file and the permissions received by each native session.
This laboratory does not modify an existing domain or a user's normal Interface
profile. The released native HTTP server binds all IPv4 interfaces; the launcher
limits the independent native viewport to half resolution for readable software-rendered
screenshots without starving the browser compositor. It protects administration
with a random token held only in the launcher process while provisioning the
fresh domain. Neither the launcher nor the atomic diagnostic writes that token
to disk or prints it. The domain configuration stores only its native verifier.
The no-input Python/JavaScript credential generators always create 32 CSPRNG
bytes, encoded as a 256-bit hexadecimal machine token. They never accept human
passwords or supplied low-entropy secrets. Their SHA-256 verifier is the format
required by the native [DomainServer HTTP Basic implementation](../../domain-server/src/DomainServer.cpp#L2952),
which hashes the received credential before comparing `security.http_password`.
It is a native protocol compatibility requirement, not a general password
storage API; substituting bcrypt or PBKDF2 would prevent the pinned native
server from authenticating administration requests.

## Actual browser and native journeys

Install Google Chrome once and run the short functional tests. The recipes below select Google Chrome; retained Firefox fixtures and past evidence remain historical. Legacy `offline-browser-alpha.mjs` and `offline-browser-zones.mjs` are not current launch recipes and must not be run under the Chrome-only scope:

```bash
npm --prefix browser-client exec playwright install chrome
OVERTE_LAB_BROWSER=chrome node browser-client/tests/integration/real-session.mjs
# Optional reviewed official Google Chrome executable (no bundled-browser fallback).
OVERTE_BROWSER_CHROME_EXECUTABLE=/absolute/path/to/google/chrome \
  OVERTE_LAB_BROWSER=chrome node browser-client/tests/integration/real-session.mjs
node browser-client/tests/integration/assets-and-avatars.mjs
```

The standard gateway also offers `overte://overte_hub`. Public admission resolves
the configured place freshly, checks actual anonymous rights and uses a separate
native worker. Arbitrary public domains and authenticated worlds are not implied
by this test. For the short actual Hub movement/native-pose/reconnect journey:

```bash
OVERTE_LAB_URL=http://127.0.0.1:8090 OVERTE_LAB_RECONNECT=1 OVERTE_LAB_REQUIRE_FLUID=1 \
  node browser-client/tests/integration/public-hub.mjs
```

These journeys require a usable actual graphics context and report measured
frame times. A successful world connection alone does not establish fluid
rendering. Public probes keep the microphone muted and do not edit the Hub.
Genuine native Tablet application proofs live under `tests/integration/tablet-*.mjs`;
the Places harness starts its own port-8093 gateway and refuses an occupied port.
Their ignored evidence preserves source identities and actual application results;
unfinished flows remain listed in the [feature inventory](../../docs/browser-client/FEATURE_PARITY.md).

The `system-firefox` variant drives the installed `/usr/bin/firefox` through
Puppeteer WebDriver BiDi, retaining the same real journey assertions. Override
the path with `OVERTE_LAB_FIREFOX=/absolute/path/firefox` when needed. The focused
asset/avatar test verifies the exact binary ATP texture SHA-256 and captures
the actual native participant beside the local browser representation.

The tests join the real domain, load its actual world and assets, verify native
and browser positions independently, change a shared object through interaction,
verify voice in both directions, leave, and reconnect. Browser microphone inputs
are **synthetic**: Chromium reads a generated 440 Hz WAV; Firefox uses its fake
media-device generator. Native input receives a generated 997 Hz tone. Captures
measure the actual independent native and browser PulseAudio outputs, rather
than merely counting received audio packets. Each has its own audio server with
null sinks and no physical hardware modules. Playwright's default Chromium
`--mute-audio` argument is explicitly removed so playback is actually tested.
Chromium screenshots use the actual CDP viewport surface directly: the clipped
Playwright screenshot path in Chromium 153 can stall after pointer lock under
SwiftShader. Bundled Firefox uses Playwright capture; installed Firefox uses
Puppeteer WebDriver BiDi capture of its actual rendered page.

Timestamped JSON results, screenshots and synthetic PCM captures are written to
`build/browser-lab/evidence`. `completed: true` means all assertions in that run
passed; `durationSeconds: 0` identifies a short journey. The 30-minute endurance
test was explicitly cancelled by the user and is not claimed as evidence. These
synthetic tests do not establish live speech quality or a physical microphone
test. Physical microphone permission/capture evidence, when available, is
recorded separately.

## Scene and asset attribution

The floor, collision wall, text, sphere and interactable box are real persistent
domain entities created by `native-participant.js`. The textured ATP glTF model
and separate 2×2 binary checker PNG texture are original fixtures generated by `create-assets.py`
under Apache-2.0. They are uploaded through the actual native Assets API, including an ArrayBuffer
for the binary PNG. The glTF resolves its relative `checker.png` dependency
through the native `atp:` service and gateway.

The separate HTTPS model is
[Box Textured](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/BoxTextured)
from the Khronos glTF Sample Assets collection: © 2017 Cesium, Creative Commons
Attribution 4.0 International, with the Cesium trademark/logo limitations listed
in its [asset metadata](https://github.com/KhronosGroup/glTF-Sample-Assets/blob/main/Models/BoxTextured/metadata.json).
The Cesium mark is used only as the unmodified sample's texture. No affiliation
or endorsement is implied. HTTPS model dependencies are fetched through the
session asset gateway; the original fixture separately proves the native
`atp:` path.
