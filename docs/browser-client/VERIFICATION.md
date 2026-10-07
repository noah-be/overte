# Browser client verification

These records describe actual local Overte domain/native/browser tests on
2026-09-30. Timestamps are UTC. The original requirement for a 30-minute session
was explicitly cancelled by the user; no endurance result is claimed.

## Environment and reproducible commands

The test host ran Fedora 44, Node.js 24.21.0, Python 3.14.7 and FFmpeg 8.1.2.
The production build and complete component test suite also passed under Node.js
22.23.3. Browser automation used Playwright 1.63.0 and Puppeteer Core 25.12.0.
The independent Interface, gateway Interface processes and domain/assignment
servers used the pinned official Overte 2026.04.1 release artifacts. Exact
public download URLs and SHA-256 identities are in
[evidence/artifacts.json](evidence/artifacts.json).

The browser rendered real entity/asset data on its own device using WebGL.
Chromium used SwiftShader in automation. Native Interface rendering used an
isolated 1024×768 Xvfb display with a half-resolution viewport; these software
rendering settings keep the native participant visible while sharing CPU
resources with the browser.

From the repository root:

```bash
npm --prefix browser-client ci
npm --prefix browser-client run build
python3 browser-client/lab/manage.py prepare
python3 browser-client/lab/manage.py start --gateway --open-browser
npm --prefix browser-client exec playwright install chromium firefox
node browser-client/tests/integration/real-session.mjs
OVERTE_LAB_BROWSER=firefox node browser-client/tests/integration/real-session.mjs
OVERTE_LAB_BROWSER=system-firefox node browser-client/tests/integration/real-session.mjs
# Optional installed Chromium; use your executable and matching library directory.
OVERTE_LAB_BROWSER=system-chromium OVERTE_LAB_CHROMIUM=/path/to/chromium \
  OVERTE_LAB_CHROMIUM_LIBRARY_PATH=/path/to/chromium/libraries \
  node browser-client/tests/integration/real-session.mjs
node browser-client/tests/integration/assets-and-avatars.mjs
node browser-client/tests/native-denial.mjs
OVERTE_LAB_BROWSER=system-firefox node browser-client/tests/integration/physical-microphone.mjs
```

The usable browser URL is **http://127.0.0.1:8090**. Its actual domain is
`overte://127.0.0.2:45102`; the pinned native release uses the equivalent
`hifi://127.0.0.2:45102` address. The alternative loopback address and domain
server IPC namespace avoid the legacy native client's global localhost-port
discovery interfering with other local test domains. Domain administration has
an automatically generated private password; unauthorized HTTP access returned
401. Startup first uploaded real entities, glTF and binary PNG assets, then
saved and verified identical anonymous/localhost guest permission groups before
starting the gateway. See [managed-start.json](evidence/managed-start.json).

The stock Chromium test used the Fedora executable `chromium-browser/chromium-browser`
and its matching extracted `usr/lib64` dependencies. These selectors apply only
to the browser child process; they do not alter native services. An installed
Chromium with its dependencies on the normal loader path needs only
`OVERTE_LAB_CHROMIUM`.

## Actual journeys

| Browser | UTC start → finish | Result |
| --- | --- | --- |
| Chromium 153.0.8010.12 | 13:49:59.987 → 13:51:25.045 | Passed |
| Bundled Firefox 155.0 | 13:51:36.245 → 13:52:37.610 | Passed |
| Installed Firefox 156.0 | 14:07:34.579 → 14:08:37.206 | Passed |
| Stock Chromium 154.0.8037.57 | 14:47:22.184 → 14:48:26.933 | Passed |
| Stock Chromium 154.0.8037.57, trusted-origin gateway | 15:18:26.663 → 15:19:36.414 | Passed |
| Stock Chromium 154.0.8037.57, final lifecycle gateway | 16:10:14.677 → 16:11:18.904 | Passed |
| Installed Firefox 156.0, final lifecycle gateway | 16:17:44.607 → 16:18:47.653 | Passed |

Every journey joined the actual domain alongside an independent native client,
loaded seven actual entities and HTTPS/ATP textured models, synchronized browser
and native movement in both directions, collided with actual world geometry,
changed a shared object's color through interaction, transmitted microphone
audio in both directions, left cleanly, rejoined, moved after reconnect, and
changed view orientation with mouse input. The native client independently
observed the browser position; measured stationary horizontal differences were
below 0.0001 m. Departed browser avatars disappeared from the independent native
client within two seconds in these runs. Each first session remained connected
without unexpected reconnects throughout its journey.

[real-journeys.json](evidence/real-journeys.json) retains timestamps, measured
positions/colors/audio levels and exact tested source/bundle SHA-256 identities.
The latest stock Chromium 154 journey ran against the final gateway security/lifecycle
and trusted-origin asset boundary and additionally hashes its permission-policy, validation and process-lifecycle
modules. These are short functional journeys, not endurance tests. Chromium viewport
screenshots use the real CDP surface because its clipped Playwright capture
could stall after pointer lock under SwiftShader. Bundled Firefox uses
Playwright; installed Firefox uses Puppeteer WebDriver BiDi. No rendered world
pixels are substituted.

## Voice and physical microphone evidence

End-to-end playback tests used synthetic input. Chromium captured a generated
440 Hz fake microphone WAV; Firefox used its generated fake microphone signal.
The independent native microphone received a generated 997 Hz tone. Native and
browser playback were captured from separate private PulseAudio null sinks,
with no physical hardware modules. Tests required nonzero signal at the actual
playback outputs and verified the known tones, rather than only counting packets.

| Journey | Browser → native playback RMS | Native → browser playback RMS | Native 997 Hz tone amplitude in browser output |
| --- | --- | --- | --- |
| Chromium 153 | 0.008598 | 0.011618 | 0.009469 |
| Bundled Firefox | 0.008081 | 0.011577 | 0.009505 |
| Installed Firefox | 0.008140 | 0.011635 | 0.009476 |
| Stock Chromium 154 | 0.008640 | 0.011323 | 0.009469 |
| Stock Chromium 154, trusted-origin gateway | 0.008642 | 0.011425 | 0.009339 |
| Stock Chromium 154, final lifecycle gateway | 0.008822 | 0.011307 | 0.009468 |
| Installed Firefox 156, final lifecycle gateway | 0.008036 | 0.011284 | 0.006084 |

A separate installed Firefox 156.0 test at **14:14:48.821–14:15:04.551 UTC**
connected to the real domain and opened a physical ALSA capture device
without fake-media preferences. One non-fake audio track was live, 52 audio
frames were sent at 48 kHz, and muting released the hardware track. See
[physical-microphone-system-firefox.json](evidence/physical-microphone-system-firefox.json).
No device labels, microphone recordings or spoken conversation were saved.
This establishes ALSA capture-device permission, frame-send and mute-release
behavior. The host reports its physical input ports as unavailable, so no
plugged-in microphone or acoustic speech input is confirmed. The bidirectional
playback proof above remains explicitly synthetic.

Chromium's actual hardware preflight at **14:23:50.711–14:23:51.633 UTC**
stopped before connection because the browser exposed zero audio inputs.
[physical-microphone-chromium.json](evidence/physical-microphone-chromium.json)
retains that failure honestly. Further actual probes of Chromium 153 headless
shell, full headless/headful Chrome, and stock Chromium 154 all reported zero
inputs and `NotFoundError`. The host has one physical ALSA capture source with
three ports, all reported unavailable. These sanitized counts are retained in
[microphone-availability.json](evidence/microphone-availability.json).
Chromium's [official PulseAudio implementation](https://chromium.googlesource.com/chromium/src/+/main/media/audio/pulse/audio_manager_pulse.cc)
excludes capture sources whose ports all report unavailable. Firefox can open
the ALSA device despite this status. No connected microphone, acoustic input or
human conversation is claimed; synthetic bidirectional playback passed.

A separate stock Chromium 154 UI test at **14:49:16.081–14:49:30.937 UTC**
used no fake microphone. It displayed “No microphone found. Connect one and
try again.”, kept all seven real entities connected, stayed muted with zero
capture frames, enabled retry, and allowed 0.420 m movement before clean leave.
It emitted no uncaught page errors. See
[microphone-unavailable-ui.json](evidence/microphone-unavailable-ui.json).
On a host with no available Chromium capture input, reproduce this with:

```bash
OVERTE_LAB_CHROMIUM=/path/to/chromium \
  OVERTE_LAB_CHROMIUM_LIBRARY_PATH=/path/to/chromium/libraries \
  node browser-client/tests/integration/microphone-unavailable-ui.mjs
```

## Binary assets, visible participants and refused access

The original checker PNG was uploaded through the real native
`Assets.putAsset(ArrayBuffer)` API. The actual glTF renderer fetched the
relative `atp:/browser-lab/checker.png` texture through the gateway. The downloaded
79 bytes exactly matched SHA-256
`18e1d2c0906dacb97f5f2bee825f1b5714c481c299e9401261ac21c0cf7b903c`.
The full journeys retain their own tested source hashes. The later focused
asset/avatar run at **15:10:33.171–15:10:54.700 UTC** records the final
gateway hash after sandbox/CSP and trusted-origin reconstruction; the production browser bundle is unchanged. See
[evidence/assets-and-avatars.json](evidence/assets-and-avatars.json).

The browser image shows its own cyan representation and the named independent
native participant in orange beside the actual models and world geometry. The
native image shows both actual humanoid participants in the same domain.

![Actual browser world, local avatar and native participant](evidence/world-native-peer.png)

![Actual native client with both participants](evidence/native-participants.png)

A separate real domain refused native connection at **13:34:49.332 UTC** because
the visitor lacked Directory Services connection permission. No world data was
exposed. Its administration required authentication, and the entire fixture ran
in an independent IPC namespace. See [native-denial.json](evidence/native-denial.json).
The gateway also validates the managed anonymous permission baseline before
releasing world/assets/audio. Login-required domains remain unsupported and
fail closed; arbitrary public domain compatibility is not claimed.

Portable records omit session/entity UUIDs, private filesystem paths,
credentials, device labels and raw audio. Screenshots retain the actual tested
pixels. Broader unit, browser and repository checks are recorded in
[STATUS.md](STATUS.md).

The native administration credential generators only accept zero inputs and
create fresh 256-bit CSPRNG machine tokens. Their SHA-256 verifier is the exact
existing native HTTP Basic format, not a human password hashing API. A new actual
refusal fixture at **15:08:50.170 UTC** confirmed authenticated administration
HTTP 200, unauthenticated HTTP 401 and refusal without world exposure.

Initial Ubuntu browser CI exposed missing display/audio backends and a
fixed-duration movement assertion. The CI environment now provides headed Xvfb,
actual software Mesa/WebGL2 and isolated PulseAudio output. All 30 browser cases
passed with those settings locally; collision waiting is bounded and requires
actual wall contact and stopped forward velocity, preserving original bounds.
No assertion or scanner rule is disabled. Remote CI results remain authoritative
and are available on [Draft PR #1023](https://github.com/noah-be/overte/pull/1023).

## Independently installed production deployment and concurrent shutdown

At **16:08:28.718–16:08:46.818 UTC**, a separately extracted production tree
installed with `npm ci --omit=dev` (only Three.js and ws, zero audit findings)
served its compiled browser on a separate loopback port. An actual Chromium
153.0.8010.12 visitor joined the real domain and independent native participant,
rendered seven real entities through WebGL2, and downloaded the exact 79-byte ATP
texture with the session asset sandbox and private no-store policy intact.

The test then overlapped browser leave with gateway shutdown while seven owned
children were still alive, sent a second SIGTERM, and awaited normal gateway
exit. All nine observed native/audio descendant processes exited; no owned
child survived, and the private session profile was removed. Teardown completed
in 5.706 seconds. Exact tested source/bundle identities and results are in
[production-shutdown.json](evidence/production-shutdown.json).

Reproduce against the running managed laboratory, after building the frontend
and installing the development/browser test tools in the original checkout:

```bash
production_tree="$(mktemp -d)"
git archive HEAD browser-client docs/browser-client LICENSE LICENSES docs/LICENSING.md | tar -x -C "$production_tree"
cp -a browser-client/dist "$production_tree/browser-client/dist"
npm --prefix "$production_tree/browser-client" ci --omit=dev
OVERTE_DISTRIBUTION_ROOT="$production_tree" node browser-client/tests/integration/production-shutdown.mjs
rm -rf "$production_tree"
```

Port 8091 must be unused; the test refuses occupied services and preserves the
primary gateway on port 8090. The separate deployment shares only the reviewed
actual domain settings and native runtime dependencies. Production source comes
from the extracted tree. It never uses a simulated world.

The final lifecycle regressions reproduce TERM-resistant child processes,
concurrent cleanup, shutdown admission refusal, rapid leave/rejoin and a
cancelled bridge write. A negative control against the old cleanup implementation
failed both new concurrent-close assertions as expected; no assertion was removed.
The final component suite passed **52/52** under Node.js 22.23.3 and 24.21.0.
The final lifecycle gateway also passed the entire actual stock Chromium 154
journey at **16:10:14.677–16:11:18.904 UTC**, including both voice playback
directions, interaction, clean native departure and reconnect. The actual
installed Firefox 156 journey with that same final gateway passed at
**16:17:44.607–16:18:47.653 UTC**.

## Expanded public-world checkpoint

The actual public `overte_hub` journey passed at
**2026-09-30 20:39:49.275–20:42:03.357 UTC** in stock headed Chromium 154 with
the NVIDIA GTX 1080 Ti. Both the initial join and a complete leave/rejoin loaded
the genuine world, supported walking on actual mesh colliders and agreed with
the native worker's position to less than one millimetre. Loaded steady samples
reached about 42–43 FPS and 33–34 ms p95 frame time. The first cold sampling
window retains its roughly one-second stall; it is not presented as uniformly
smooth initial loading. Versions, source hashes, isolated worker boundaries,
motion and frame measurements are recorded in
[public-hub-rendering.json](evidence/public-hub-rendering.json), with an
[actual browser image](evidence/public-hub-browser.png).

This run requested no microphone and sent no public entity/asset writes.
It proves public-world rendering, movement and reconnect for this audited
domain, not arbitrary public-server compatibility or public voice conversation.
Its cached Tablet helper predates the ongoing text-focus correction; full
Tablet app behavior remains a separate acceptance requirement. The subsequent
native feature parity and graphics/optimization goals remain open.

An actual cabana material-group comparison preserved all 7,428 oriented
triangles, UVs, normals and material membership, with zero rendered pixel
changes while reducing three draw groups to two. The bounded opaque grouping
matches the native serializer; transparent and uncertain ordering is preserved.
See [baked-fbx-material-grouping.json](evidence/baked-fbx-material-grouping.json).

The original packaged default mannequin was independently checked against six
fixed native QResource files: every repository/browser asset matched the native
release bytes exactly. Its two real skins and 14,748 triangles render in both
Chromium and Firefox. The native idle pose independently captured offline at
21:12:05 UTC agrees with all 67 canonical browser bones within one millimetre
(maximum measured error 0.142 mm); both original skins deform. The shared
identity binding children inherit their parent's pose exactly once. The
[avatar audit](evidence/default-avatar-rig.json) distinguishes this packaged
resource/rig proof from pending public participant and actual Emote app tests.

The complete genuine Tablet Snap/files/People journey passed in stock Chromium
154 at **21:04:14–21:05:28 UTC** and stock Firefox 156 at
**21:11:41–21:12:52 UTC**. It exercised native Snap capture of the visitor's
WebGL scene, actual PNG and animated GIF export, exact visitor file transfer,
native Unicode avatar rename, selected-text export and clean leave. The GIF
frame-duration correction and integrated current production package still need
their follow-up verification; full Tablet completion is not claimed here.

## Expanded implementation checkpoint (2026-10-01)

Genuine two-participant native Tablet Chat exchange passed in stock Chromium154
and Firefox156, with Unicode text sent through the native MessageMixer and
shown in the original Qt UI. Both microphones remained muted. These results
prove Chat exchange; notifications, moderation and complete app parity remain
pending in the feature inventory.

The actual Firefox Hub journey at21:30:09–21:32:23UTC on2026-09-30 loaded
297–298models/75mesh colliders, walked with native replication and reconnected
without page errors. Its16.9–20.8FPS steady rendering did **not** pass fluidness;
see [public-hub-firefox.json](evidence/public-hub-firefox.json).
Subsequent read-only native-model comparisons verified conservative static
batching: the dominant actual Hub FBX fell from1190to62drawcalls while all
53836triangles, material identities and33transparent groups remained intact.
The original transparent Mesh ID and its exact geometry are restored; actual
Chromium/Firefox WebGL images differ only at up to3Float32 boundary pixels and
restore exactly. This focused asset proof does not replace the pending fresh
whole-Hub Firefox frame-time and movement/reconnect test.

New Chromium/Firefox component journeys passed visitor Bookmark/Home persistence
across reload, stale-authority refusal and malformed gateway-message recovery.
The latter uses a real local WebSocket: the browser sends application close4002,
cleans up the world and joins again without page errors. Protocol-reserved1002
is rejected by the [browser WebSocket close API](https://websockets.spec.whatwg.org/#dom-websocket-close);
it is therefore unsuitable for client-initiated close.

All34required dependency-light repository checks passed again (175.81seconds).
Updated native/browser runtime additions still require a fresh production archive,
voice/interaction/reconnect evidence and exact-head CI. No endurance test ran.


## Later actual proof and restricted source continuation

The later strict Hub journeys passed all unchanged fluidness gates in stock
Chromium154 (23:03:11–23:05:19UTC) and Firefox156
(22:59:10–23:01:16UTC), including initial/rejoined walking with native pose error
below one millimetre. See [public-hub-fluid.json](evidence/public-hub-fluid.json)
for exact source hashes, native runtime, GPU, measurements and commands. The
sessions were always muted and made no public world writes. Earlier failed
Firefox measurements remain historical evidence.

The genuine corrected native Snap/files/People flow passed in Chromium154
(23:20:08–23:21:18UTC) and Firefox156 (23:30:48–23:31:53UTC). The actual exported
GIF duration was 5,000ms in both runs. These results do not verify unrelated apps.
The two-fresh-native-worker persona restoration proof is recorded separately in
[visitor-persona-native.json](evidence/visitor-persona-native.json); browser UI
persistence and the later display-name overflow correction need current proof.

After the platform restriction, source work continued only in a temporary copy.
The frozen continuation's `npm run build` passes under Node 24.21.0/npm 11.19.0,
including TypeScript, Vite and complete license notices. The existing Vite large
chunk warning remains visible; it was not disabled. No actual browser or native
session was launched for this new bundle.

```bash
node --import tsx --test --test-isolation=none src/*.test.ts tests/*.test.ts
```

This frontend/offline diagnostic run reported **164 tests: 162 passes, two
failures**. Both actual packaging tests fail at `spawnSync git EPERM`. No test
was skipped or weakened. This diagnostic loader avoids the prohibited `tsx` CLI
IPC socket; it does not replace the required standard full suite. A full combined
attempt with `gateway/*.test.mjs` cannot start its global real-network setup
(`listen EPERM`), so its cascading setup failures are not source verdicts.

A separate 22-file gateway run reported **81 tests: 78 passes, three failures**.
Its files are clipboard-wire, fluid-performance, managed-network, native-avatar,
native-bridge, native-navigation, native-output, native-session, native-tablet,
native-world, navigation, places-override, public-places, session-races,
socket-heartbeat, tablet-chat, tablet-files, tablet-qml, tablet-snapshots, tablet,
visitor-persona and visitor-preferences, all under `gateway/*.test.mjs`. The three
failures require genuine loopback listeners and fail at `listen EPERM`:
clipboard-wire, native-session and socket-heartbeat. Earlier missing repository
script context in the temporary copy was restored read-only before this final
run. Passing VM/source tests do not establish live native transport or UI proof.

The current tests cover unchanged parser geometry/transforms, native opacity and
texture-binding precedence, actual Three LoadingManager deadline/cancellation,
private shader trust/cloning/static-batch guards, bounded alpha backpressure,
FST/material cleanup and intermediate replacement ownership, visitor persona and
production teardown ordering. ImageBitmap/Worker fault inputs are explicitly
mocked where Node lacks browser primitives; those are not real browser evidence.

An independent [shipping native CPU audit](NATIVE_FBX_AUDIT.md) reran eight
original/generated FBX inputs and six negative controls successfully after its
final SPDX header update. It confirms all twelve Kim materials use effective
native opacity one and the actual albedo/opacity filename bindings. It does not
load images or establish corrected browser visibility. Exact linked native
library, source and input hashes are in the sanitized report.

The prepared, unintegrated Zone module passed 27 unit tests and TypeScript;
[ZONE_IMPLEMENTATION.md](ZONE_IMPLEMENTATION.md) records its precise source
revision, limits, pending ambient/shadow adapter and three unrun browser cases.
Do not remove unsupported-effect warnings or claim rendered native parity.

Independent capability probes fail on temporary topic writes (EROFS), temporary
loopback listeners (EPERM) and offline browser launch/IPC (EPERM); escalation is
unavailable. The new material pixels, visual Kim, alpha-corrected strict Hub,
current full movement/voice/interaction/rejoin, production-only distribution,
required checks for the integrated continuation and exact-head CI remain pending.
No restricted execution was bypassed. The continuation is uncommitted and not
applied to the topic. A durable patch/hash/source artifact is in the canonical
checkout's ignored `build/browser-client-continuation`; it is not a release.
No endurance test was run.
