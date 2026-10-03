# Direct browser client status

Updated: 2026-10-03 (Europe/Berlin). Goal is active. Acceptance is **not yet demonstrated**.
The user narrowed ongoing browser work to Chrome only. Firefox results below
were completed before that scope change; no further Firefox tests are planned.

## Completed preparation

- Read the complete user session specification and repository working,
  contribution, architecture, branch, source ownership, and testing policies.
- Created a persistent Codex Goal without a token budget.
- Fetched the authorized fork's `main`; created the requested topic and isolated
  worktree at `d569930678d2edb61330a96bcdcab17ee68a732f`.
- Validated the branch name before creation and installed/verified the reviewed
  reference-transaction and pre-push guards. Version:
  `4d7c7ccdfd9f46f44cc54f0e8e8d265bcbabb9bfc6781c01fa60acf75cd88f24`.
- Started parallel read-only investigations of transport compatibility,
  immutable browser reuse, and isolated build/test prerequisites.

## Observed preparation facts

- `libraries/shared/src/shared/WebRTC.h` disables `WEBRTC_DATA_CHANNELS` on the
  current supported server platforms. `WEBRTC_AUDIO` enables audio processing,
  not a browser DataChannel endpoint.
- Historical WebRTC signaling, socket, and server routing code remain behind
  the disabled DataChannel compile guard. Their presence does not establish a
  working browser connection.
- The concurrent browser renderer has reusable device-side interfaces. Its
  gateway session and streamed native tablet do not satisfy this task.

## Current work

The optional native server transport and current production Chrome client are
built. The feature remains OFF by default. The final source-bound ON build
passes six selected native CTest programs; a separate default-OFF build passes
real domain/assignment builds and three selected generic-policy programs.
The current browser source passes 320 tests, strict TypeScript and the production
build. The refreshed repository quick profile passes 34 suites after the final
launcher/qualification/CI changes.

The direct ServiceWorker-to-session-worker asset route is implemented and tested
with actual owned MessagePorts and native AssetServer bytes. Four fresh Chrome
profiles on one frozen production bundle pass in direct/page/page/direct order.
Complete-scene loading averages 126.1166 s direct versus 178.7999 s page: **29.46%
shorter** in this software-only sample. All 55 models, available maps, geometry,
image sizes and graphics settings match. Pixel differences from authored/live
motion are retained; this does not qualify hardware performance.

The earlier production snapshot's full `direct-chrome-20261003-e` journey passes
25/25. The current route's f journey passes 24/25 but remains failed after its
host launcher disappears and the unchanged freshness guard correctly rejects
keyboard verification. Two regressions reproduce the orphaned-driver failure
before its cleanup fix and pass afterward. The independent bounded `direct-chrome-20261003-g` journey then passes **25/25**
on the same current production artifact, with a freshly qualified native actor
and genuinely unused version-2 motion trial. Both position directions, actual
body draws, input/collision, both synthetic audio directions and clean
leave/reconnect/error handling pass. Earlier failures and consumed trials are
preserved separately.

The public native qualification workflow now emits the validated observer/source
fields needed by the browser launcher itself. Actual new-launch ordinary spawn,
separate placement, loaded HTTPS/ATP assets and all six service endpoints pass
without private post-processing. Root helper checks pass 10 launcher, 7 host-action
and 7 public visitor-qualification regressions.

One original dock PSD remains unavailable; actual geometry/material values render
with an explicit incomplete-texture warning and no substitute pixels. Chrome's
actual stock microphone denial/allowance, virtual capture and complete stop pass
their separate two-case diagnostic. **Physical bidirectional speech and hardware
fluidity remain unqualified.** Software cadence is 1.248–1.674 fps in the controlled
route comparison. Public Hub access needs operator-side server upgrades and has
not been qualified. The topic is published as
[draft PR #1034](https://github.com/noah-be/overte/pull/1034). All remote checks
for code head `00c68dc31d6137ee8cc6d2d81dc25cf41dac68f8` have completed
successfully. The Goal remains active while physical acceptance is pending.
Detailed immutable-run evidence and hashes follow below.

## Verified checkpoint

- Actual C++ generated packet versions/signature and 1424-byte datagram limit.
  The signature also matches the executed native 2026.04.1 release.
- Strict TypeScript and production browser build passed. Browser unit suite:
  320 passed, zero failed/skipped in the current direct-asset-port build, including lifecycle, reliable
  header boundaries, real worker MessageChannels, minimum Zone selection and
  native null/Any/IPv4 socket records.
- Actual domain/assignment binaries and all three new native tests built.
  All six selected CTests passed in 1.92 seconds in the final source-bound build,
  with `QT_QPA_PLATFORM=offscreen`,
  `--timeout 45 --no-tests=error`: projection/permissions and actual Qt socket
  records, native avatar/audio serialization, real RTC ingress/lifecycle, and
  existing packet, received-message and sequence-statistics programs.
  No test was skipped. Native fixtures check the same UTF-8 ATP strings,
  full-file ranges, avatar pose/traits/QString and PCM bytes as the browser.
- A separate fresh configuration omitting the feature argument records the
  actual default `OVERTE_BROWSER_TRANSPORT:BOOL=OFF`. Its real domain/assignment
  builds and three unchanged generic-policy native programs pass, with Qt totals
  8/7/7 and zero failures/skips. All 739 compile commands, expanded links and
  ELF/resolved dependencies exclude DataChannels. Existing WebRTC audio remains
  an actual pinned linker input. This qualifies the selected native subset,
  not all five ordinary networking programs or Interface.
- Explicit optional native CI ownership: 33 regressions passed. No existing
  native test is excluded. The dedicated lane enables the feature, builds real
  servers, checks its CTest inventory and bounds each program at 45 seconds.
- Required repository quick profile: 34 suites passed, zero failed in 186.44 s after the final launcher/qualifier/CI changes.
  Command: `python3 tests/run-project-tests.py --profile quick --timeout 240`.
  Evidence: ignored `build/browser-direct/checks/20261003-direct-asset-port/repository-quick-post-launcher.log`.
- Historical software browser smoke before the Chrome-only instruction passed for Chrome for Testing 153.0.8010.12
  (SwiftShader), Playwright Firefox 155.0 and stock Firefox 156.0 through BiDi
  (Mesa llvmpipe). All six local tablet apps, live graphics callback,
  disconnected microphone controls and actual failed-domain error/peer cleanup
  passed without uncaught app exceptions. Evidence and exact frozen bundle
  hashes: ignored `build/browser-direct/e2e/smoke-20261002-d/`.
- After the Chrome-only scope change and minimum Zone implementation, the
  frozen production bundle passed `smoke-20261002-f/` in Chrome 153.0.8010.12:
  all six local apps, graphics changes, failed-domain errors and peer cleanup;
  zero uncaught exceptions. This smoke did not join a native domain.

Hardware GPU devices were absent from browser/native test namespaces. The driver
cleaned only its registered processes. Software UI/error success does not yet
establish complete world/audio acceptance or hardware fluidity. Direct native
join is separately demonstrated by the actual Chrome scene probes below.

## Actual historical Hub scene

The source is the immutable repository snapshot from 2019-12-06, SHA-256
`f104f22166f4a085240291bb3ac800eb510b08aee19320055a7e32a16599a509`.
Its representative selection has 83 actual entities including 55 models, with
parent transforms, collision/rendering/material properties retained. Original
selected scene SHA-256:
`13017c3233d1cb9edfb1b9a9df80445b002c5ed700409964c4c30bba255c46a2`.
Remote scripts are omitted in this isolated lab.

Downloaded actual assets initially covered 375 files and 133,652,513 source
bytes. Importing actual Zone skybox/ambient closures expanded this to 389 files,
239,553,156 source bytes, including three EXR and 144 KTX files. Its enumerated
manifest reports zero failed downloads; discovery does not include PSD references.
The actual baked dock material later exposes one unavailable original PSD outside
that enumerated closure. The largest imported file is 33,554,792 bytes, within
the 64 MiB individual bound.
Native visitors can select the same texture metadata's compressed variants.
Geometry/image bytes are unchanged; textual absolute CDN references
change to equivalent ATP paths with both source/served hashes recorded. All
asset bytes and credentials remain in ignored private lab storage.
The actual CDN supplied no CORS permission for this browser origin. The initial
ATP-derived scene changed 55 model URLs. Its preserved derived scene hash:
`41f60920188877f1fc65c6cc8b2e0b0d841c767360f4877f974764fb9c260e79`.
A separate own HTTPS/CORS fixture serves actual bytes; its request/hash/CORS
check passed. See `LAB.md` and the private provenance manifests. This is
historical scene evidence, not a live public Hub test.

The next qualification uses a separately hashed mixed scene: the existing Hub
bridge model retains its original relative model/material/texture closure over
the own HTTPS fixture; the other 54 models and eight Zone image references use
equivalent ATP paths. All original geometry, image bytes and transforms are
retained. Asset-manifest SHA-256:
`005d92e2cf3f5907ee3dc01e5086947b65d4f954d664c0ed044fb52bbf1850d9`.
Mixed scene SHA-256:
`7038f0e796b069a1e0f3ceaa64456e13ba2c0a8bf7306b326d9031bf19aa96ad`;
the corresponding all-ATP scene with Zone sources is
`9982ab70d21b1421bcd7b4bdccf9fe8806a31d0b46a4a46b8a174a037b937e55`.
The browser now supports the actual contained daytime equirectangular EXR
skybox, with actual full-resolution background draws in Chrome/native probes;
ambient/key-light/haze/bloom and other native Zone effects are not claimed.

## Commands and results

Executed from the canonical reviewed checkout unless stated otherwise:

```text
git fetch origin main
python3 tools/branch-policy/check.py check-name --branch feature/main/browser-direct-client
python3 tools/branch-policy/install.py install
python3 tools/branch-policy/install.py status
git worktree add -b feature/main/browser-direct-client /home/user/Documents/github/overte-browser-direct-client origin/main
```

Results: branch name accepted; installed safeguards verified and matched reviewed
source; worktree created successfully. Later results appear in the checkpoint.

## Outstanding acceptance

The current direct-asset-port Chrome/native journey passes all 25 functional criteria,
including movement/collision/interaction, actual native-body synchronization,
both synthetic audio directions and session cleanup. Actual Chrome consent UI
also passes separately. Remaining acceptance is physical bidirectional speech,
and smooth navigation on an available hardware GPU. The default-OFF native
compatibility build and refreshed 34-suite repository checks pass. The topic
and draft PR are published; all remote checks for the code head pass. The
[manual hardware and speech procedure](MANUAL_ACCEPTANCE.md) prepares the
remaining human-assisted checks; its hardware steps have not been executed.

The earlier image-sharing comparison does not establish a full-scene speedup.
The subsequent direct/page/page/direct comparison passes all four cases on
unchanged asset bytes and recorded quality, with mean full-scene loading
29.46% shorter through the direct local port. Its software-only scope and
nonidentical PNGs are documented below. Keep physical microphone evidence
distinct from synthetic PCM. Local software results do not establish
hardware fluidity or public Hub support. No issue is closed or marked completed
by this work. Complete geometry and available-map loading are qualified, with
the unavailable original PSD explicit.

## Chrome direct-domain checkpoint

The uninterrupted Chrome run `build/browser-direct/e2e/direct-20261002-b/`
joined the actual native domain in 3.27 seconds, received 83 real entities and
the Hub spawn, moved through trusted keyboard input, produced a real PNG
snapshot, and rejoined to receive 83 entities again. No uncaught application
exception was recorded. The native visitor received the browser's actual pose.
The run correctly failed asset rendering, native identity and full peer cleanup.

The reliable SDK sender authenticated a copied packet and discarded that copy,
so its transmitted ATP and identity packets had source ID zero. The native
asset server rejected them. This is being repaired on the browser sender;
native source/HMAC verification remains enabled. The unused RTC peer and closure
lifecycle were repaired. Explicit native UDP binding now retains the advertised
source address across reliable replies and socket rebinding.
These failures are preserved as baseline evidence, not reported as acceptance.

The repaired sender/lifecycle/HMAC code passed its focused regressions and
strict TypeScript. SDK provenance now verifies 117 exact inputs, 30 documented
adaptations and six explicit omissions, including an audit of original Git
objects. Actual same-path asset cleanup and reply-header boundary regressions
passed after review found those two additional defects.

The first strict-UDP-bind lab restart exposed incorrect lab assignment-subnet
configuration and a legacy child-monitor address. It was withdrawn from ready
state, and the bounded Chrome run `direct-20261002-c` correctly timed out and
closed every RTC peer without an uncaught exception. The lab now gates readiness
on all six real assignments. Native named-path spawn reached the real Hub pose,
but successful spawn alone did not qualify the missing assignment services.

The next native-only diagnostic briefly admitted all six services, then its
assignment monitor exited with SIGSEGV (139). Source inspection identified an
actual null dereference: status from the explicitly bound `127.0.0.3` child was
rejected by a localhost-only branch, then dereferenced anyway. The repair admits
only native UDP from legacy localhost or the configured native interface,
validates the status size/type, and returns safely when no child node exists.
Readiness must remain stable across several child-status intervals before the
next browser run. Earlier missing sockets were process death, not evidence of a
STUN hang; no speculative STUN workaround has been added.
The monitor repair built in both actual native binaries and passed all six
selected CTests in 1.31 seconds. A scoped curl certificate probe returned HTTP
200, while default trust rejected the fixture certificate. This did not prove
that the native visitor's Qt network stack trusted the certificate. Its first
actual Qt request still failed TLS; process-local system-bundle mounting is
being qualified separately. A new runtime will be qualified after the final RTC
admission review.

That native build and all six CTests passed in 1.38 seconds, with no skipped
programs. Its immutable runtime SHA-256 was
`fe0599767f6c3aceb95123234ead97229b0020736d98bf979d61df96f2392c6e`.
All six actual assignments passed three consecutive seconds of authenticated
readiness, bound to both registered domain/monitor process identities. This
runtime served the bounded Chrome rendering probe while native test-client
loopback routing and scoped Qt certificate trust are being qualified. A further
RTC ingress length check will require a fresh tested runtime afterward.

Chrome-only rendering probes `scene-probe-chrome-20261002-a` and `-b` qualified
that runtime and all six services but failed during domain admission. Actual
exception stacks identified a `RangeError` in the historical SDK's fixed-size
`DomainList` socket reader. The native services had used standard STUN fallback
and Qt serialized a null public address without four IPv4 address bytes. The
shared bounded reader now handles null/Any/IPv4 records, preserves domain UUID
byte order, and rejects malformed/unsupported addresses with visible session
cleanup. Fixture bytes were generated by the pinned Qt 5 build; nine focused
browser wire tests and strict TypeScript pass. The actual production native
stream-operator tests were then added to the consolidated build. SDK provenance
verifies 117 exact inputs, 30 documented adaptations and
six omissions, including audited original Git objects.

The corrected production browser build (`index-D5ZDhiDk.js`, 386 modules) passes
all 161 unit tests with zero failures/skips and strict TypeScript. The final
RTC ingress and native stream-operator fixture changes built in both actual
server programs. All six selected CTests pass in 1.53 seconds, with zero failed
or skipped Qt cases. Fresh immutable runtime SHA-256
`363563931983e8e127ab636ef770c2fdb2191ca086b8ae932e392c25e3eeee34`
passes the stable all-six/process-identity readiness gate. Corrected Chrome
probe `scene-probe-chrome-20261002-c` joins in 3.13 seconds, receives all 83
source entities, and reaches the ordinary historical Hub spawn. Its rendering,
asset and lifecycle result is still in progress.

The actual packaged native visitor's Qt HTTPS requests now load the unchanged
Overte mannequin FST/FBX, with 69 joints, two meshes and 9,198 vertices. This uses
a CA bundle mounted only inside that visitor's isolated namespace. A separate
native-only setup records its ordinary spawn before placing that participant
three metres ahead for visible-peer checks. Native world entity loading remains
unqualified: an actual EntityQuery reached its distinct server send thread, but
the visitor still reported zero nearby entities on the previous runtime.

Probe `scene-probe-chrome-20261002-c` subsequently passed exact small ATP
FST/FBX/PNG hashes, snapshot, leave/all-peer closure and fresh reconnect, with
zero uncaught/shader errors. Its HTTPS requests failed during TLS negotiation
with the original Ed25519 laboratory certificate. The fixture now uses a
separate RSA-2048/SHA-256 certificate; old certificate and negative evidence are
preserved privately. Chrome accepts only that fixture's configured public-key
pin, and native Qt uses only its process-local CA mount. System trust and normal
TLS verification are unchanged.

Fresh probe `scene-probe-chrome-20261002-d` passes actual Chrome HTTPS/CORS/hash
reads and actual historical HTTPS bridge rendering: 3,920 source triangles,
ten main-camera draws and the unchanged 1024×1024 sRGB JPG. Both real avatar
models load. Image `https-rendered.png` and live model/Zone diagnostics are
preserved in its ignored evidence directory. Full model/texture completion
still failed its bounded wait; the selected original EXR returned HTTP 502
before decoding. Native AssetServer bytes were arriving but reliable messages
with missing fragments did not complete. Source inspection found an inverted
SDK loss-interval predicate; three real-connection loss/reordering/retransmission
regressions failed before correction and pass afterward, including sequence
wraparound, exact payload bytes and cumulative ACK progress. A fresh production
Chrome result remains pending this repair.

The same run exposed an unsolicited historical directory public-key request on
an anonymous flow. Key generation now requires an actual authenticated account
and username; anonymous challenges preserve empty native credentials. The real
AccountManager regression and strict TypeScript pass. Probe `-d` records no
metaverse requests after this guard; server authentication remains authoritative.

## Isolated loading measurement

`tools/benchmark-assembly.ts` replayed an actual unchanged Hub FBX (1,824,496
bytes, SHA-256 `7018393b1c1f88e51650eb80cab77cfd62da38528159dd25555cb476731b0a53`)
through 1,311 native-MTU fragments in five alternating paired runs. Median
assembly time was 465.54 ms for repeated concatenation and 3.82 ms for the
bounded one-allocation implementation. Every reconstructed byte/hash matched.
Evidence: ignored `build/browser-direct/assembly-performance.json`.
This measures message assembly only; world loading and texture-decoding
comparisons remain pending.

## Remaining large-asset diagnosis

Frozen Chrome probe `scene-probe-chrome-20261002-e` used production bundle
`index-CtanyVQH.js` and native runtime `363563…`. Direct admission, all 83
entities, ordinary spawn, original small ATP/HTTPS hashes, actual HTTPS bridge
draws, snapshot, full peer closure, reconnect and unavailable-endpoint errors
passed. There were zero uncaught or shader errors. Model completion still
failed its 90-second stage (one loaded, six active, 34 queued); the later
90-second Zone stage failed before EXR decode with HTTP 502 (two loaded, six
active, 18 queued). The loss-interval fix is independently regression-tested;
it has not resolved this remaining end-to-end failure.

The next bounded diagnostic uses the separate actual `DirectSession` asset
entry without automatic world/model/image requests, together with read-only
native AssetServer RTT/window/ACK/retransmission metrics. Its production asset
timeouts, bytes, mapping/get protocol and content checks are unchanged. This
will distinguish transport progress from simultaneous renderer work and queued
large replies. Results do not qualify the scene or a quality-preserving loading
improvement.

The same Chrome probe exposed unconsumed native mixer silence, environment and
stream-statistics controls. Native silence now produces one exact 960-byte
stereo zero frame after current-mixer/session, PCM and 480-sample checks.
Optional bounded environment/statistics records are consumed; Zone reverb is
not implemented or claimed. Three focused regressions pass against the actual
native silence fixture, including empty-codec PCM equivalence, truncated
frames, wrong service/revoked session and unsupported sample counts. Real
synthetic/physical voice interoperability remains pending.

Two further regressions exercise the actual mixed-PCM and negotiated-codec
listeners: both fail before correction with uncaught native-parser RangeErrors
and pass afterward. Every prefix of the native stereo PCM fixture is rejected
without playback or page exceptions, while the complete frame preserves exact
sample bytes. Codec records must have an exact bounded length and select PCM
or its empty-name native equivalent; invalid records do not alter codec state.
All five focused mixer cases and strict TypeScript pass. This is parser
validation, independent of the still-pending bidirectional voice evidence.

## Native world receipt after endpoint repair

Fresh immutable runtime
`f114b8dc5d0541e813f580ce33b9e26353d61e14b8a3bfb82f2afe8ce3381177`
passes all six bounded native CTests in 1.40 seconds with no failed or skipped
cases. The real native regression executes authenticated PingReply processing,
actual endpoint activation, UDT HandshakeACK and a reliable native octree
completion packet. Wrong-port traffic preserves the advertised endpoint.

An explicitly loopback-bound server now uses a registered native peer's observed
loopback address when its verified reply has the same port as the advertised
endpoint. The change is restricted to that address mismatch; wildcard binds,
nonloopback traffic and RTC peers retain their existing behavior and packet
authentication. This aligns the outgoing reliable queue with incoming native
handshake/ACK state.

The unchanged packaged native visitor (2026.04.1), on the same actual source
scene and ordinary Hub spawn, now receives 53 nearby entities and loads all
34 ATP models visible to it. Its original HTTPS bridge loads one mesh with
4,404 vertices and 11,760 indices. The previous zero-entity result is preserved
as negative evidence. This qualifies native world receipt/model loading;
Chrome/native visible-avatar, input, voice and loading comparisons remain
independent requirements. Any later native-only placement is recorded
separately from ordinary spawn and does not alter the browser pose.

## Isolated real Chrome asset result

`asset-probe-chrome-20261002-a` passes all six steps in Chrome for Testing
153.0.8010.12, using test-only entry `asset-probe-Dj21Cg05.js` and native runtime
`f114b8dc…`. It fetches the unchanged original daytime EXR (4,143,539 bytes,
SHA-256 `592887f589416ff2e4186025ad5f7bfbba3cf788d84f7868673eda8a84ede5c3`)
in 2.605 seconds, and the original waves FBX (1,824,496 bytes,
SHA-256 `7018393b1c1f88e51650eb80cab77cfd62da38528159dd25555cb476731b0a53`)
in 0.869 seconds. Both virtual ATP fetches return HTTP 200 and exact bytes.
All 2,977 EXR and 1,311 FBX wire parts complete; there are no observed gaps,
30 retransmission/duplicate observations, advancing ACKs and no uncaught errors.
This result measures the real direct transport without scene rendering, and
does not establish a full-scene loading improvement.

The existing native AssetServer's authenticated read-only metrics show 0–2 ms
RTT and 13.513 Mbit/s peak throughput in this diagnostic. After explicit leave,
only the actual native visitor remains as an Agent in the domain and the
AssetServer peer count returns from three to two. There are zero RTC failed
writes after the recorded end boundary. Exact frozen bundles, private
per-session metrics and lifecycle checks remain in ignored lab evidence.

Two additional browser regressions expose and repair receive-state cleanup:
unfinished fragments now reach the actual failure handler on channel disposal,
and address/message keys have an explicit separator so decimal concatenations
cannot collide. Both tests fail before correction and pass afterward. The
consolidated `npm test` suite now passes 175 cases with zero failures/skips,
including five independent transport-header observer cases. Strict TypeScript
and the 386-module production build pass. Current SDK provenance is 116 exact
inputs, 31 documented adaptations and six omissions, verified against the
immutable original Git objects. The next full-scene Chrome run uses production
artifact `index-BMnz2K1A.js` on the same qualified native runtime and scene.

## Full-scene Chrome contention measurement

`scene-probe-chrome-20261003-f` used that frozen production artifact, the
unchanged mixed Hub scene and native runtime `f114b8dc…`. Direct admission,
83 entities, ordinary spawn, both identities, exact small ATP/HTTPS hashes,
actual HTTPS bridge draws, snapshot, leave, reconnect and endpoint errors pass.
There are no uncaught or shader errors. Full model completion still fails its
120-second stage at seven loaded, six active and 28 queued; a later observation
has nine loaded, six active and 26 queued. The original daytime EXR fails with
HTTP 502 before decode and has no qualifying sky draw.

The browser records 492 long tasks totaling 171.532 seconds, with a 424 ms
95th percentile and 852 ms maximum. Concurrent native AssetServer metrics on
the same loopback/runtime show browser RTT of 350–861 ms, throughput of
0.071–0.920 Mbit/s and up to 157 retransmissions per sampling window, compared
with 0–2 ms RTT and 13.513 Mbit/s peak in the renderer-free diagnostic. This
supports main-thread contention as a cause of delayed protocol processing;
the next bounded Chrome CPU profile will identify the responsible work before
changing production scheduling. Rendering quality and asset bytes remain fixed.

Header diagnostics observe 12.844 MB and 9,486 AssetServer datagrams at the
failed completion boundary, 8,167 unique reliable packets, 977 repeats, no
tracked sequence gaps and the ACK at the highest observed sequence. The bounded
message observer evicts 137 records; missing parts after a record reappears do
not establish network loss because its earlier observation history is absent.
These wire observations are separate from SDK delivery and asset completion.

After explicit end the browser process registry is empty, the domain retains
only the native Agent, the AssetServer returns to two peers and there are zero
post-end RTC failed writes. Private evidence is under the probe directory and
`build/browser-direct/lab/runtime/asset-stats-scene-probe-f-summary.json`.

## Chrome worker capability and next frozen profile

`feature-probe-chrome-20261003-a` verifies the stock Chrome 153.0.8010.12
worker-transfer API without app/native connections or network sends. A real
unordered, zero-retransmission RTCDataChannel transfers to a DedicatedWorker
in its creation task. The worker receives the actual connecting channel and
exposes RTCDataChannel, while RTCPeerConnection is absent. A transfer in a
later task fails with the expected DataCloneError. All peers, workers and Blob
URLs are closed/revoked, and the own process registry is empty afterward.
This establishes API capability independently of application qualification.

The next full-scene CPU profile uses frozen production `index-9ek2Xw0Z.js`.
All 177 browser tests pass with no failures/skips; strict TypeScript, production
build and both immutable renderer/SDK provenance audits pass. The profile is
bounded to ten seconds of whitelisted function/stack/source metadata and is
mapped against the same frozen bundle's source map. It captures no heap,
network payloads or object values. Assets, quality and model timeout are fixed.

The resulting `scene-probe-chrome-20261003-g` still fails full-scene completion:
four models loaded, six active and 22 queued at the 120-second boundary. The
daytime EXR returns HTTP 502 without decoding. Its ten-second CPU capture spans
10.347 seconds and 7,002 samples: 90.66% is attributed to `(program)` outside
identified JavaScript; `Socket.readPendingDatagrams` accounts for 7.18%
inclusive and HMAC processing for 4.78% inclusive. These overlapping figures
do not identify HMAC as the dominant cost. There are 489 observed long tasks,
165.194 seconds total, with a 415 ms 95th percentile.
Concurrent native metrics record up to 747 ms RTT and 0.279 Mbit/s throughput.
Natural end again leaves the native Agent and two AssetServer peers, with zero
post-end RTC failed writes and an empty browser process registry.

## Implemented worker path, awaiting real Chrome qualification

The entire DirectSession, source/HMAC verification, UDT ACK/reassembly and ATP
hash validation now run in one DedicatedWorker. The page creates and transfers
each actual RTCDataChannel before offer generation or sending; subsequent peer
control uses a separate bounded MessagePort. No raw datagrams traverse the
page. ServiceWorker fetch reply ports transfer directly to the native core.
The page supplies viewport, asset base and its persisted anonymous fingerprint.

The renderer acknowledges one outstanding event; avatar/permission snapshots
coalesce and ordered entity edits remain ordered, with at most 32 queued events.
Pose updates similarly retain only one posted and one newest pending pose.
Leave immediately revokes page asset authority and closes native peers; a new
join awaits both core leave and peer reset acknowledgment. Entity domain links
use that same boundary. Audio PCM uses an AudioWorklet-to-worker port with epoch
checks and a ten-frame (100 ms) credit bound; live frames are dropped when the
consumer stalls, rather than accumulating delayed speech on the page.

Strict TypeScript and the 20 focused broker/SDK lifecycle regressions pass with
real transferable MessageChannels and mocked native RTC control. Nine focused
worker-runtime regressions passed in the first worker freeze. Three runtime cases failed before correction:
a queued connect could reopen a retired session, the legacy audio path ignored
remote mute, and unattached playback could accumulate page messages. These
tests now pass, alongside stale audio epochs, bounded playout credit, direct
ATP port authority, ordered/coalesced events and fingerprint injection.
SDK provenance currently verifies 115 exact, 32 adapted and six omitted inputs
against original Git objects. These are controlled software results; actual
worker Chrome rendering, voice and loading improvement remain unqualified.

Independent review then identified a terminal-worker recovery defect: an entry
failure left an already-disposed core while the page still permitted reconnect.
Terminal entry/bootstrap and actual Worker errors now retire the owned Worker
and peers immediately, with a reload-required error; they are handled even when
bootstrap carries an older initialization generation. Recoverable event-queue
overflow retains the ordinary reconnect path. Four additional public-facade
regressions pass, including pending ATP cancellation and actual port cleanup.
The complete worker freeze has 215 passing tests, zero failures/skips, with
strict TypeScript, both original-object provenance audits and production build
passing. Its artifacts are `index-ERa6qrVp.js`,
`session-worker-COwUsU0U.js` and `audio-worklet-D2cpBBu8.js`.

## First actual worker Chrome result

`scene-probe-chrome-20261003-h` uses those frozen artifacts, native runtime
`4534e078…` and unchanged mixed-scene/asset manifests. Actual transferred
worker DataChannels exchange native packets, direct admission receives all 83
entities, and ordinary browser spawn passes. It reaches seven loaded models
and 11.794 MB of observed AssetServer data by about 40 seconds. Native numeric
metrics show 0–5 ms RTT and 4.211 Mbit/s peak throughput during the short active
window, compared with the earlier main-thread run's 747 ms and 0.279 Mbit/s.
These are separate diagnostic checkpoints, not a paired full-scene or
equal-quality loading benchmark.

The browser initiates a domain disconnect at 23:23:28 UTC. Native logs show its
disconnect request before Agent removal and no preceding timeout, authentication
or version rejection in the inspected window; all six services remain stable.
The first browser-side cause was not retained and is still unknown. Full-scene
rendering and ATP representatives therefore fail, while HTTPS byte checks pass.
The avatar preference step also used a transient notice that was overwritten by
model-loading progress; the timeline independently records its successful
preference notice. A direct saved-state assertion will replace that brittle
check without relaxing the identity requirement.

This run ends early as an interrupted negative diagnostic, with original
progress, timeline and CPU evidence retained. Every main peer and actual worker
channel is closed, the browser registry is empty, the domain retains the one
native Agent, AssetServer peers return to two, and there are zero RTC failed
writes after end. It does not qualify the complete user journey.

A further runtime regression fails before correction because asynchronous
page-requested core leave callbacks overwrite the page's existing error with
"Disconnected". Cleanup callbacks for that explicitly requested retirement
are now suppressed; spontaneous native/core errors remain visible. All ten
focused worker-runtime regressions and strict TypeScript pass. The next short
Chrome probe also adds passive bounded first-error history before join and
fails promptly after an unexpected session end; native code, world bytes,
rendering quality and production asset deadlines remain unchanged.

## Confirmed renderer queue pressure and correction

`scene-probe-chrome-20261003-i` uses production `index-Dav6b8gq.js` and
`session-worker-D1wbB-11.js`. Its 218-test freeze, strict TypeScript, production
build and both provenance audits pass. Passive bounded error observation now
records the first cause exactly: event-queue overflow at 69.574 seconds. This is
a recoverable renderer-pressure failure, rather than a native timeout or an
uncaught page error. Leave, fresh reconnect and unavailable-endpoint checks pass;
natural end leaves one native Agent, two AssetServer peers, no own browser
processes and zero RTC failed writes.

Direct admission, 83 entities, ordinary spawn, saved avatar preference state,
and original FST/FBX/image hashes through both ATP and HTTPS all pass. Before
overflow the last observation has 20 models loaded, six active and 28 queued;
the actual daytime EXR is ready at its original 4096×2048 resolution, with 80
observed main-view background draws. The partial native participant has its
actual two-mesh rig attached; visible avatar draw/input/voice acceptance remains
separate. No complete-scene PNG was reached. The 180-second native trace includes
two transient browser sessions across reconnect, with 0–6 ms RTT and 11.6195
Mbit/s peak throughput. These are diagnostic measurements, not full-scene or
paired equal-quality loading evidence.

The real scene has eight entities with angular velocity, so native simulation
legitimately changes their exported rotations and produces full entity replies
about once per second. Empty removal events and repeated unsent property
records accumulated behind a busy renderer. The outbox now skips empty edits
and retains each entity's newest unsent full record, merging only across
independent avatar/permission snapshots. Nonempty deletion, full snapshot and
all lifecycle events remain ordering barriers; an already posted update is
never modified. The 32-event cap is unchanged and merged records are bounded at
65,536. Two new coalescing/order regressions fail before correction and pass
afterward; the resource/retirement case also passes.

The resulting `scene-probe-chrome-20261003-j` freeze passes all 221 browser tests,
zero failed/skipped, strict TypeScript, production notices and both immutable
source audits. It uses `index-8269GU94.js`, `session-worker-BZUicwTG.js` and the
unchanged `audio-worklet-D2cpBBu8.js`. Native runtime, scene/asset manifests,
rendering quality and production deadlines are unchanged. Its full-scene
Chrome result remains negative: the unchanged 120-second completion step
fails, and the later observation settles at 54 loaded models with no active or
queued model loads. One model has failed permanently; its exact retained cause
will be established before changing the loader. An optional original PSD image
also encounters the historical CDN's expired certificate; the bridge's baked
JPG textures still load and draw. Fixture-only trust does not bypass that
external certificate failure.

All other scene-probe criteria pass. The session stays admitted beyond the
previous overflow boundary, and passive worker observation records no fatal
error. The actual HTTPS bridge submits six main-view draws and 23,520 triangles
with its assigned textures; the original 4096×2048 daytime EXR submits 193
background draws. Snapshot download, leave, fresh-channel reconnect, unavailable
endpoint handling and the six local tablet applications pass, with zero uncaught
application exceptions and zero shader errors. Independent inspection of both
private PNGs confirms textured bridge/Hub geometry, the daytime sky and the
actual local mannequin. A remote native label alone does not qualify remote
avatar body rendering or native position synchronization.

The unchanged native AssetServer trace covers 180 seconds of the admitted
browser session: RTT 0–8 ms, peak 11.1823 Mbit/s, maximum congestion window six,
47 retransmissions in the largest reported window and zero duplicate packets.
Sampling ends before the browser's final lifecycle steps; these are diagnostic
metrics, not a paired equal-quality benchmark. After natural end, the browser
registry is empty, one native Agent remains, the AssetServer returns to two
peers and there are zero post-end RTC failed writes. Twelve in-run failed-write
records require separate timestamp/lifecycle classification. No zero-during-run
claim is made.

Timestamp correlation places the six printed warnings before the first
Connected sample. Six later suppression summaries print during normal fresh
reconnect. No unsuppressed warning prints during the long Connected stage, but
individual suppressed occurrence times are unavailable, so this does not
establish zero actual failures during that stage. Native Agent removals match
the ordinary final leave and short fresh reconnect; cleanup stays qualified.

The ten-second CPU profile attributes 96.07% of retained sample time to
`(program)` outside identified JavaScript; it does not identify a remaining
JavaScript bottleneck. Full-scene completion, input/collision acceptance, native
avatar interoperability, synthetic and physical voice, hardware fluency and
the paired loading comparison remain unqualified. Private evidence is retained
under `build/browser-direct/e2e/scene-probe-chrome-20261003-j/`.

The independent runner-stop tests also pass three real-process regressions,
including a fresh nonexistent private state parent. CI runs this Python check
after the browser tests; it does not require GPU or native lab resources.

## Isolated permanent-model diagnostic

`model-probe-chrome-20261003-a` uses the same production app, all 83 native
entities, ordinary spawn and unchanged assets/settings. Its explicitly
diagnostic-only 55-second bound preserves the exact failed current model and
catch reason, then naturally leaves; it does not qualify full-scene rendering.
Read-only per-entity states are bounded to 128 rows, and a private WeakMap keeps
retired-root reasons from leaking into replacement roots. Two bounds/lifecycle
regressions and a batched transient-notice retention regression pass. The
consolidated freeze has 224 passing tests, zero failures/skips, strict TypeScript,
production build and both original-object source audits passing.

The actual failed dock-pieces baked FST reports a session texture image failure
at about 43 seconds. The historical original FBX's expired-CDN PSD request is
specified by the actual baked material JSON itself: all 50 PBR materials point
at the original `bridges_d.psd`, rather than the neighboring baked image files.
This disproves the initial FST-remapping hypothesis; no remapping defect is
claimed. The source PSD's availability and native/browser decoding behavior
are being investigated. Recovering unchanged source bytes is preferable to
substituting an unrelated baked image. No asset substitution, quality reduction
or longer deadline is accepted as a substitute for establishing the cause and
correct material rendering.

Verified source recovery checks currently fail: the exact original CDN request
has an expired certificate, both historical-path Overte mirror candidates return
404, and the actual CDN's TLS-valid CloudFront alias returns 403. No source PSD
bytes or substitute pixels have been imported. A PSD decoder dependency is not
added without the actual file/format.

The primary native behavior in
`libraries/procedural/src/procedural/ProceduralMaterialCache.cpp` treats a failed
texture as finished so geometry can fade in. The browser currently rejects the
whole model when that image fails. A native-compatible correction will retain
the actual geometry and declared material colors while explicitly recording and
showing incomplete textures. It must keep revoked-session/abort failures closed;
it does not qualify the unavailable original PSD or full original-texture parity.

The packaged native visitor independently retains the same dock PSD texture
failure in its log; sanitized private evidence is
`build/browser-direct/lab/runtime/native-psd-texture-log-inspection-4534.json`.
Native geometry readiness is therefore separate from complete original texture
readiness as well.

## Refreshed physical resource prerequisites

The read-only 2026-10-03 resource inspection finds one suspended physical ALSA
source, with its Front Mic, Rear Mic and Line In ports all unavailable. No physical
source is opened. Foreign native/gateway/Xvfb registrations remain live, their
namespaces expose DRM devices, and both foreign Xvfb processes retain DRM render
descriptors. This proves device access, not a measured renderer workload or an
exclusive lease. The lab's `hardwareAllowed=false` is a constant conservative
policy pending an agreed window, not a GPU utilization measurement.

The user test-window question remains unanswered; elapsed time or a preselected
option does not grant an exclusive window. Hardware/physical-microphone tests
have not started, and software/synthetic tests continue independently. Evidence
is private `build/browser-direct/lab/runtime/physical-resource-readiness-20261003.json`.

## Current native observer and provenance checkpoint

The native-visitor-only restart for motion observation keeps server runtime
`4534e078…`, scene and assets unchanged. This later launch automatically reaches
ordinary Hub spawn, without the earlier path retry, and observes 53 nearby
entities, 34 ATP models, the real HTTPS bridge and its 69-joint/two-mesh avatar.
Ordinary observation precedes the separate native-only three-metre placement.
Earlier startup negatives and ordinary/placement evidence remain preserved.
The new native observer and motion readiness bind to this current process;
no move/restore trial has occurred yet. AssetServer baseline is freshly measured
at two stable peers, rather than reusing the prior native visitor's identity.

Renderer provenance now requires SHA-256 and modification notices for each
adapted file. Six real-file/original-Git-object regressions pass with zero
failures/skips. Default and explicit source-checkout audits verify 89 exact
renderer files, six documented adaptations and all 95 original Git objects.
The immutable original Woody license/contributor metadata and the Overte import
are recorded in `browser-direct-client/REUSE.md` and bundled attribution;
the six native avatar resource bytes remain unchanged.

Before publication, the final native source/build checkpoint will add prominent
modification notices while preserving existing attribution, including restoring
the original creator lines in the rewritten WebRTCDataChannels pair. Current
native functional probes continue against the frozen runtime first. Final
default-OFF server compatibility builds will use a separate directory and no
libdatachannel prefix, without reconfiguring the live ON laboratory.

## Native-compatible texture failure and complete geometry observation

The renderer now retains actual geometry, declared material values and all
successful maps when a genuine source image fails, as native NetworkMaterial
does. Abort or retired asset authority still fails the load. A bounded per-FST
failure memo avoids repeatedly fetching the same unavailable source; it never
persists across sessions/root reloads. The separate persistent UI warning reports
incomplete objects even after later model progress notices. Two focused material
regressions pass, including a fail-before/pass-after reproduction and actual
abort/revocation with another successful exact-pixel map.

The frozen `scene-probe-chrome-20261003-k` has 236 passing browser tests, zero
failures/skips, strict TypeScript, production build, both renderer audits,
SDK provenance and all three Python launcher checks passing. Main artifact
`index-BnwLmr6K.js` SHA-256 is
`3afb68f56f59c0c22d9ad562a245e9a897bf852e45488f488775109b1837647f`;
the native session worker is unchanged `session-worker-BZUicwTG.js`.
Native server runtime, original assets, geometry, material values and production
deadlines remain unchanged.

The unchanged 120-second scene step fails, and the immediately following
explicit-PSD check samples before the final models finish. These negatives are
retained. At 00:51:23 UTC, the independent timeline observes all 55 models loaded,
zero failed/active/queued/compiling models, and exactly one incomplete dock model
with one unavailable original PSD and ready shaders. This qualifies complete
geometry observation after the bound; it does not establish timely 120-second
completion or recover the original PSD. Independent inspection of the actual
PNG confirms the real textured Hub scene and local mannequin.

All other scene criteria pass: direct 83-entity admission, ordinary spawn,
identity, exact ATP/HTTPS representative bytes, main-camera HTTPS bridge and
full-resolution Day sky draws, snapshot, leave, fresh reconnect and visible
failed-endpoint cleanup. There are zero uncaught application/shader errors.
The 180-second native trace has 178 browser-present samples, RTT 0–5 ms, peak
12.798 Mbit/s, maximum congestion window six, largest reported retransmission
window 64 and zero duplicate packets. It ends before the browser probe; natural
cleanup leaves the current native Agent, two AssetServer peers, an empty own
browser registry and zero post-end RTC failed writes.

The next full direct/synthetic-audio journey uses a fixed 180-second software
scene wait based on this observed completion. This changes only the outer test
wait; native 20-second asset requests, ServiceWorker/image deadlines, all 55
geometry/shader requirements and explicit unavailable-texture evidence remain
intact. Both performance arms must use identical fixed bounds/settings. The
120-second negative is not relabeled a pass, and full original-texture parity is
not claimed. Trusted canvas focus precedes the actual jump. New pose evidence
must prove fresh native receipt after trusted keyboard movement and fresh
Chrome body geometry/draws after the separately labeled native-only move/restore.

## Current immutable native generation checkpoint

Runtime SHA-256
`4534e078914a7efa22d37f78661ea5a805cda745db69d71b8e486b807a2aab9a`
passes all six selected native CTests in 1.89 seconds, with zero failed/skipped
cases, and the stable all-six strict-UDP readiness gate. Native regression
coverage includes RTC generation retirement, queued reliable sends, current
node ownership and preserved native UDP behavior.

Its packaged native visitor initially remained at the origin on two startup
attempts; those negatives are retained. One normal native `hifi://` path lookup
retry then reaches the actual Hub spawn and independently observes 64 nearby
entities, all 45 visible ATP models, the original HTTPS bridge and the actual
69-joint/two-mesh mannequin. Initial automatic spawn is explicitly unqualified;
ordinary native path retry is recorded. The separate three-metre native-only
placement occurs after that ordinary evidence and does not move the browser.

## Full direct Chrome journey: complete geometry and synthetic downlink

`build/browser-direct/e2e/direct-chrome-20261003-a/` naturally ends at
01:05:50 UTC with an empty own browser process registry and an overall negative
result. The unchanged production/native generation passes all 55 geometries,
available maps and default avatar in 155.082 seconds within the fixed 180-second
scene wait. The exact original unavailable dock PSD remains the only incomplete
model, with a persistent warning and no substituted image bytes. Ordinary spawn,
identity, exact ATP/HTTPS bytes, real HTTPS main-view draws and the actual Day
sky also pass.

A real native synthetic 523.25 Hz input reaches the actual Chrome Pulse output
monitor: RMS 0.02617, matching amplitude 0.01530 versus 0.0000485 at the separate
659 Hz reference, 383,814 captured frames and native audio receipt increasing
from 36,321 to 37,216. This establishes the synthetic downlink only. No physical
microphone, bidirectional voice or user audio permission acceptance is claimed.

The native peer evidence fails closed because the isolated Node driver tries to
inspect a host PID through its private PID namespace. The real native observer
remains alive; neither movement direction is qualified by this failed guard.
The correction will keep PID isolation and perform actual process identity and
bounded native motion operations in the host-owned runner, with private
run-bound request/results. The synthetic-audio helper does not have this PID
namespace issue and needs no added relay.

Trusted pointer-locked yaw passes. Picking targets the genuine HTTPS bridge,
but the third-person camera-to-hit distance is about 5.33 metres, outside the
unchanged five-metre interaction bound; the next test selects first-person in
the actual Avatar application. A jump predicate observes upward velocity but a
second delayed sample catches a later phase and fails the separate assertion;
the next driver retains evidence atomically from the successful predicate.
Tablet visibility is not restored after a failed world step, causing subsequent
capture/snapshot/leave/reconnect UI failures. These negatives remain preserved;
the runner will restore the real UI before each independent tablet test.
No production transport/rendering change follows from these harness defects.

After this run ends, prominent modification notices are added to modified
native sources and Python routing checks. The original WebRTCDataChannels
creator lines are restored. These comment-only edits do not change the running
4534 generation; the final native build and default-OFF verification will be
bound to their own updated source/build hashes.

The direct-a AssetServer trace has 180 samples over 180.018 seconds, all with
the browser present: RTT 0–4 ms, peak 10.491 Mbit/s, maximum congestion window
five, largest reported retransmission window 48 and zero duplicates. It ends
at 01:00:41 UTC, before journey completion, and is not a paired benchmark.
The cleanup observation confirms one current native Agent, no other Agents,
two AssetServer peers and zero post-end RTC failed-write records. The lifetime
record count is 36; no zero-during-run claim follows. Result SHA-256 is
`bcf4f9d7687c1ddd57f61b96000ac9d1d524c1c4d5c676b8da2e9d3af938cc15`;
trace SHA-256 is
`e77e7bf8209375dbbeadc4ddd689d9ece512e9cdc934bf32d6da1405671b34fd`.

## Host-owned native test actions and bounded paired measurements

The frozen harness passes the following independent checks from
`browser-direct-client/`, with zero failures/skips:

```bash
python3 e2e/native-host-actions.test.py  # 6 tests
python3 e2e/run-control.test.py          # 3 tests
node --test e2e/time-budgets.test.mjs e2e/native-motion-evidence.test.mjs  # 3 tests
```

The host runner verifies the exact live native PID/start tick/executable/cwd,
current native session and fresh actual observer sequence. A host-generated
nonce binds each private request/result to this run. Only the fixed once-only
native move/restore test operations are allowed; requests expire after five
seconds, jobs after twelve. Reads require an owned private regular file and
use no-follow/nonblocking descriptors, so a FIFO or substituted link cannot
stall the watchdog. Subprocesses join the owned registry and cleanup restores
an applied native test move. The browser retains its private PID/device
namespace. CI now runs both Python harness suites explicitly.

`direct-chrome-20261003-b` starts with the same frozen Bnw/BZU browser artifacts,
4534 native runtime, observer, source assets and RSA fixture. The driver selects
first-person through the actual Avatar checkbox, retains the real five-metre
hit requirement, saves jump/landing evidence atomically and restores the tablet
around independent input steps. Results remain pending until its natural end.

The paired cache measurement has one common 240-second scene deadline starting
immediately before trusted Join, a 285-second entire fresh-profile case deadline
including browser setup, and a 1200-second four-case batch limit. The direct
scene's 180-second wait starts after identity/asset checks, whose time already
overlaps actual loading; these timing origins must not be compared as identical
durations. The new benchmark allowance is explicit and applies equally to both
arms. All 55 model/shader criteria, the exact unavailable PSD evidence and
production request/image deadlines remain intact. Both cache modes use distinct
fresh profiles in on/off/off/on order and identical source/served hashes and
settings. Actual live angular-entity/native-avatar changes and pixel differences
are reported; pair pass means functional/loading/budget criteria, rather than
automatic pixel equivalence. No loading-speed improvement is claimed before
these measurements run.

## Braced Hub interaction and actual Chrome pointer-lock recovery

`direct-chrome-20261003-b` ends naturally at 01:40:27 UTC with an empty owned
browser registry and an overall negative result. All 55 model geometries and
available textures pass in 156.720 seconds, alongside ordinary 83-entity join,
identity, representative exact ATP/HTTPS bytes, the explicit original PSD warning,
actual HTTPS shader draws and Day sky draws.

The host process proof succeeds. The actual native observer independently has
the browser's current identity and position within about two millimetres of the
browser sample. The saved `native-avatar-visible.png` also shows the actual
wooden native rig/body in the main view on the original textured bridge. The
full peer step remains failed: after its screenshot, the driver cannot restore
the tablet because Chrome remains pointer locked after Playwright Escape. No
native move/restore is invoked and neither motion direction is qualified.

A later real source-entity click reaches the exact Hub bridge's braced UUID.
`DirectSession.sendInteraction` passes that string to the SDK's canonical-text
UUID constructor, causing a BigInt conversion exception and terminal worker
failure. Subsequent input/audio/lifecycle failures are retained. The correction
normalizes only paired braces at this packet boundary, preserves original entity
map/UI keys and reports malformed identifiers without throwing or transmitting.
The unchanged SDK UUID implementation/provenance is retained. Two real production
packet-writing regressions fail before and pass after the correction: actual
braced/bare/uppercase UUIDs serialize the same native 16-byte value and method
payload, while malformed current identifiers produce a bounded error and no
packet. Native admission/source/HMAC checks are unchanged.

The separate `input-probe-chrome-20261003-a` takes 2.11 seconds in isolated Chrome
153.0.8010.12. It proves the exact harness cause: trusted Playwright Escape keeps
the pointer lock, while the existing trusted T application shortcut releases it
and restores the actual tablet, after which normal toggle clicks work. There are
zero page errors and the owned registry is empty. Its explicitly test-only capture
setup joins no domain and claims no movement/scene/audio acceptance. Production
input/CSS is unchanged; the corrected driver uses that real shortcut and one
outer cleanup around peer evidence to preserve primary failures.

The direct-b AssetServer trace has 180 samples, with the browser present in 175,
RTT 0–7 ms, peak 12.386 Mbit/s, congestion window at most six, retransmissions up
to 71 per reported window and zero duplicates. It ends at 01:35:03 UTC, before
journey completion. Cleanup confirms one native Agent, no other Agents, two
AssetServer peers and zero post-end RTC failed-write records; the runtime
lifetime count is 48. Result SHA-256:
`6e3b9d6ad8a8d1f7eb426515aa04d6ceeda01359d270c91dc5900dcd45b82353`;
trace SHA-256:
`b555711fae74f2e47c8c510d1eea6c6c3ae4c0c86585646a954ee29b0888e1d1`.
No cleanup count establishes zero failures during the complete admitted stage.

## Chrome direct-c: trusted input, native visibility and two retained negatives

`direct-chrome-20261003-c` ends naturally at 02:04:38.738 UTC with an empty owned
browser process registry. Its overall result remains negative. All 55 real
model geometries, available maps and the default avatar pass in 158.831 seconds
within the unchanged 180-second scene wait. Direct 83-entity join, ordinary
spawn, identity, exact representative ATP/HTTPS bytes, real HTTPS bridge draws,
the full 4096 by 2048 Day sky and the exact original unavailable PSD warning pass.
No replacement pixels or full original-texture parity are claimed.

The loaded native participant has the actual identity, pose and 69-joint,
two-mesh rig; its body submits main-view draws. The saved
`native-avatar-visible.png` is independently inspected and shows the native
wooden body on the original textured bridge. This establishes visibility, not
complete native animation/material parity. Trusted pointer-locked mouse yaw,
the actual source-entity pick, a 900-millisecond trusted keyboard move received
as a strictly newer same-session native peer pose, and jump/landing on the
actual Hub model triangles pass. The braced-UUID packet correction therefore
also passes the actual original Hub interaction. Snapshot, leave, fresh
reconnect and unavailable-endpoint cleanup pass; page and shader errors are zero.

Native synthetic input at 523.25 Hz again reaches the actual Chrome output:
383,418 captured 48 kHz frames, RMS 0.023001, matching amplitude 0.023630 versus
0.00001755 at 659.25 Hz. This is synthetic downlink evidence only. The
browser-to-native criterion fails because Chrome exposes no microphone from
the private monitor-only Pulse source; actual sent frames remain zero and the
application displays its no-microphone error. A separate private remap source
over that synthetic monitor is being prepared for real Chrome getUserMedia.
No physical source or Chrome fake-device flag is used.

The fixed one-metre native X move succeeds, with actual observer sequence
2619 to 2621 and X advancing about 1.039 metres. The later body confirmation
fails and its error is masked by the finally block's rejected restore. After
stepping across the narrow original bridge, native gravity settles the
participant 1.086 metres below its saved height, outside the unchanged one-metre
restore guard. This run does not qualify native-to-browser movement or restore.
The once-only trial remains consumed; its guarded failure is preserved. The
harness will retain primary/body/cleanup evidence separately. A fresh native
visitor will use a separately versioned one-metre move along the real bridge's
Z direction, retaining the original scene, amplitude, height/session/replay
guards, ordinary-spawn proof and fresh native qualifications.

Frozen browser production artifacts for this run:

- `index-Dd1gADIq.js`, SHA-256
  `01c055a325ff7ffc28b427aea6616caf4e23a2e59753bf8d1d61057eb6f63eee`.
- `session-worker-X5s-NMLr.js`, SHA-256
  `6ea9b0347a69d236a34ae858023403621b772d7972cbd76c9999a5fad7d9fd5d`.
- Worker source map, SHA-256
  `d810e1f8cb01b0cd5c2ab69c5903818902900ab242d48f67809fbf65c38f8444`.
- `audio-worklet-Dh5YJhbv.js`, SHA-256
  `966ccb298ddb5f3339442a8989ee11238c34987b1f0227b9ef6ac14e53e71931`.

Strict TypeScript/production build and all 239 browser unit tests pass, with
zero failures/skips. The native runtime remains the immutable 4534 generation.
The direct-c AssetServer trace has 180 samples, with the browser present in 173,
RTT 0–6 milliseconds, peak 10.643 Mbit/s, congestion window at most seven,
retransmissions up to 86 per reported window and zero duplicate packets. Its
180-second window ends before the journey. Cleanup confirms one current native
Agent, no other Agents, two AssetServer peers and zero post-end RTC failed writes.
The runtime lifetime count is 54; zero-during-run success is not implied.
Result SHA-256:
`215570aea2c2670e98b4e1f5cbe50128f99eeff0655a4427076db3781c24e775`;
trace SHA-256:
`d64700ab5999dcc5269b63d518e568d0d56881ac1a04d3dfb358a6089710a0ce`.

## Native joint semantics and Chrome synthetic capture correction

Independent source review after direct-c identifies an actual avatar projection
defect. `DirectSession.publishAvatars` replaces SDK null default flags with
identity rotations and zero translations. Native `Rig::copyJointsIntoJointData`
sends absolute rig-frame rotations and parent-relative model-coordinate
translations; `Rig::copyJointsFromJointData` restores native defaults and converts
absolute rotations to parent-relative before applying the bones. The copied
renderer instead directly applies absolute rotations to local bone transforms.
The direct-c native body is visible, but its unusual silhouette does not qualify
correct native joint pose.

The projection now retains raw nulls, native parent indices, authoritative
skeleton defaults and scalar scales. It copies joint/default objects before
queueing worker snapshots. Three real SDK `AvatarData`/`ScriptAvatar` publication
regressions fail before and pass after: initial defaults, animated-to-default
native receiver flags, and independence from later mutable SDK data. Exact
command from `browser-direct-client/`:

```bash
./node_modules/.bin/tsx --test --test-reporter=tap tests/direct-session-avatars.test.ts
```

The SDK/native wire format is unchanged. Renderer absolute-to-relative mapping
passes three fail-before/pass-after regressions; an actual Chrome/native pose
comparison remains pending. Model-coordinate
translations are not assumed to be metres. The original renderer objects and
adapted-source hashes/notices will remain explicit.

The private browser Pulse server exposes `browser_microphone`, a remap source
whose only master is its owned synthetic null monitor. The short actual Chrome
`media-probe-chrome-20261003-a` passes in 1.59 seconds: Chrome enumerates audio
inputs and opens an enabled live 48 kHz mono getUserMedia track. Every track is
stopped and the owned browser registry is empty. No fake-device flag or physical
source is used. This qualifies the synthetic capture setup only; actual native
uplink, physical microphone and visitor permission-prompt acceptance remain
unqualified.
Result SHA-256:
`cfa2ee376c27657bdc8bc2bd9fb6ad4acc1e42c261ab7a0ae90e176c88a2c75c`.

## Frozen corrected renderer and native motion fixture

The corrected AvatarRig follows the native receive path: choose actual loaded
default poses for nulls, convert nondefault absolute rig rotations into model
space, then remove parent rotations using the actual loaded hierarchy. Original
model-coordinate translations, authored bone scales and the outer native Y180
turn are retained. Three new regressions fail before and pass after, including
an animated parent/child, return to nonidentity defaults and declared authoring
rotation. The original copied rig test remains byte-exact. Explicit bounded
passive evidence now captures actual source null/default/hierarchy fields and
the loaded bone/owner/default transforms without modifying their state.

Independent focused verification passes 10 renderer/pose/draw cases, five
motion/primary-cleanup cases, seven host relay cases, three launcher cases and
six provenance-checker regressions. The relay and native movement checks reject
stale version-1 fixtures; launch binds the exact current observer source hash.
Native body, restore and tablet failures are recorded separately. The 32
actual-source VM motion checks pass; they do not qualify real native movement.
The strict original height, session, process, expiry and once-only guards are
unchanged.

The full suite passes 251 cases with zero failures/skips in 2.89 seconds;
strict TypeScript and production build pass in 2.38 seconds. Renderer provenance
passes 87 exact inputs/eight adaptations and all 95 original Git objects. SDK
provenance remains 115 exact/32 adapted/six omitted with original-object checks.
Renderer manifest SHA-256:
`73320533e7d745b104e4011ef5d56f2ec6891fd7ac8539accf9b1c586fc79640`.
Frozen artifacts recorded under ignored
`build/browser-direct/checks/20261003-avatar-freeze/`:

- `index-BrPaCUW_.js`, SHA-256
  `1bdd31bcf9ab5fe6ffdd556650bd531ad351db511c22fb00f3399a53da707a4e`.
- `session-worker-sMmmmsx7.js`, SHA-256
  `a3ed8ca784cb4cb091843dcb0350491622171f5ea5bc56f20f45f370d0010e68`.
- The native-framing worklet remains `audio-worklet-Dh5YJhbv.js`, SHA-256
  `966ccb298ddb5f3339442a8989ee11238c34987b1f0227b9ef6ac14e53e71931`.

The fresh version-2 native visitor is qualified against the unchanged 4534
services and actual scene. Its initial automatic spawn is negative; the ordinary
native `/` path retry reaches the actual Hub spawn, observes 64 nearby entities,
45 ATP models, the 69-joint/two-mesh rig and exact native-Qt HTTPS FST/FBX bytes.
A separately labeled native-only three-metre placement follows that proof.
The one-metre Z motion trial is unused at launch. Four named native joints are
captured through read-only APIs with parent-relative model and absolute avatar
object spaces explicitly labeled. They are separately timed samples, not an
identical-frame or full animation-parity comparison. No joint setter is used.

Native observer source SHA-256:
`d45e18cd1f8b80aba49c3f5511262a80df2b164972b6e7ffd60bb73f0759a9d1`;
visitor qualification SHA-256:
`4790484703125123218d852a140571c018559328cf181cbf38ec9977befd7f4a`;
all-six readiness SHA-256:
`7f2301e55d9a19a701b8d52083315135687abf62ffc42acc0f95c1469f6e0dc9`;
four-joint evidence SHA-256:
`d0a27f12a6429621eb28ae8650eb0f1e5f9c2d6e1db12ca5b38dae6ac99578a5`.
The native 64/45 view is not compared as equal loading work with Chrome's 83/55.

`direct-chrome-20261003-d` uses `--mode direct --audio --timeout 180`
against these frozen artifacts and an initially unused guarded trial. The
complete result is recorded below. A separate 180-second AssetServer trace is
bounded independently. No native/source/service change or competing CPU build
occurs during the run.

## Chrome direct-d: 24 passing criteria and stale native peer updates

The journey ends naturally at 02:57:55.457 UTC with exit code 1 and an empty
owned browser registry. It takes 11 minutes 49.5 seconds across the individual
bounded operations. Twenty-four of 25 criteria pass; the complete journey is
**not passed**. All 55 actual model geometries and available assigned maps finish
in 154.37 seconds under the unchanged 180-second scene wait. Actual HTTPS bridge,
Zone skybox, 83 entities and the corrected upright native rig submit real draws.
Independent image inspection confirms the basic upright body; it does not
establish full native animation, material or effects parity. The original
unavailable dock PSD remains explicit, with no substituted pixels.

Trusted yaw, real entity picking, browser movement reaching a strictly newer
native peer pose, actual bridge-triangle jump/landing, snapshot, leave,
reconnect, failed-domain handling and zero uncaught/shader errors all pass.
Synthetic native 523.25 Hz audio reaches 383,397 actual browser output frames:
RMS 0.0266625, reference amplitude 0.0114851, competing 659.25 Hz amplitude
0.0000351728. Actual Chrome microphone capture and native audio transmission
advance from 130 to 1,050 frames. Its 659.25 Hz synthetic reference reaches
384,480 actual native output frames: RMS 0.0593047, reference amplitude
0.00815715, competing 523.25 Hz amplitude 0.000312066. Both use the isolated
owned Pulse sources. A physical microphone and visitor permission prompt remain
unqualified; the automation permission grant is explicit in the result.

The native-only fixed negative-Z move succeeds in the same session: observer
sequence 459 to 461 to 470, displacement Z -1.02573 m/Y +0.14890 m, followed by
strict restoration of the exact original pose. No cleanup failure is present.
Chrome's six body observations over 15.2 seconds retain the original owner
position, bounds, source position and 69-joint/default snapshot byte for byte.
This identifies stale data at the renderer boundary; it does not yet identify
whether the source wire update, SDK receive or worker delivery is responsible.
Native observer sequence numbers describe script observations, not AvatarData
wire sequencing. The native trial is now consumed/restored and cannot be replayed.

The separate AssetServer trace has 180 samples, 168 with the browser present,
RTT 0–7 ms, peak 11.3056 Mbit/s, congestion window at most eight, at most 78
reported window retransmissions and zero duplicates. It ends at 02:48:58 UTC,
before the motion operation and journey end, and does not cover the whole run.
Cleanup confirms one current native Agent, no other Agents, two AssetServer
peers and zero RTC failed-write records after the end. The runtime lifetime
count remains 54; this is not a zero-during-run claim.

Ignored evidence SHA-256:

- Complete result: `818e7076b53feeae2c6fd3f30386c97440070447a0e7941a4abd725a4b5eff0b`.
- Browser audio output: `c8e9e1b168c5d2933550d92272b8192276ddfb0b372a91c6dbc5f56582d65138`.
- Native audio output: `ed8d5681de9f0090646a62e18c0c8e2ff50aac2aa2fa71dcc699f3bc48b185db`.
- Native motion/restore proof: `4667a4b37d9ac6a60a7ce9ce2cfb626dc8856255cabb4d9d237c32c23d0957d0`.
- AssetServer trace: `07dcc9d30e237bec9c2cd680ab98d3c40f1539cfcf859b81f5a0a086852c9159`.
- Cleanup: `062763ad5119285976bba2ebcb1fe405d59a4218da81c23e71a56530aca93ba2`.

The equal-quality four-profile loading benchmark remains held while stale peer
updates are diagnosed. Required final native build/default-off verification,
repository checks, commits and draft PR remain open. All new browser runs use
Chrome only.

## Stationary Chrome avatar receive diagnosis

`avatar-probe-chrome-20261003-a` ends naturally at 03:42:04.887 UTC with
exit code 0 and an empty owned browser registry. All three diagnostic collection
steps pass. The isolated page uses the unchanged production session worker
(`a3ed8ca784cb4cb091843dcb0350491622171f5ea5bc56f20f45f370d0010e68`),
the actual SDK and the actual `WorkerDirectSession` callback. It does not create
a rendered world or request model/image assets. There is no native movement or
microphone request; ordinary core silence packets remain active.

During the 15.43-second observation window, 43 new native first-record body and
joint checksums reach the raw DataChannel observer. The outgoing worker avatar
events and actual facade callbacks each show 43 joint pose changes. The separate
native getters change seven times. Across the whole join, all 47 observed
complete ordinary `BulkAvatarData` packets have the expected native first record,
version 55 and a finite global position. There are no unsupported layouts,
fragments, other first-record peers, page exceptions or scene asset requests.
Stationary global positions agree. This demonstrates fresh idle joint delivery
without the rendered world; it does **not** qualify changed-position delivery or
replace the failed full-journey criterion.

The native API's local avatar hash key appears as the literal string `null`
after `String(id)`. Native `MY_AVATAR_KEY`, the exact own pose/name and the sole
current DomainServer Agent establish that this is the local self entry. The
diagnostic excludes only that guarded alias and retains refusal of any other
participant. Ignored source-bound classification SHA-256:
`60d6a6dd86104c6edea3bf07e01a64f8edc2fb48d2021ba4e0ebdc2c4176f527`.

Complete diagnostic result SHA-256:
`3d63ebf66eb935dd24be0875d8304c9b3b18fa07d1aa85688a3f5fcecf39843a`.
Final diagnostic driver SHA-256:
`877c570223334e5fa57f5d39b6054fbf8f71b06942d0c1c180ed26b7f5014c89`.
The separate passive AvatarMixer sampler starts after this run's end and has
zero admitted-window coverage. Its later counters are not attributed to this
diagnostic. A fresh, separately guarded quiet motion diagnosis is being prepared;
the full 25-criterion journey and equal-quality benchmark remain open.

The 03:33:25 UTC read-only physical-resource recheck still finds the physical
audio source suspended with all microphone/line ports unavailable. Two foreign
native-display process trees hold DRM descriptors; descriptor ownership proves
device access, not workload intensity or an exclusive test lease. No physical
capture or hardware graphics context is opened. The user's optional timing
question remains unanswered. Readiness artifact SHA-256:
`044ca994fd1be670eebccf86754898c4955f30695fd3bdbff08831d70750104b`.

## Reproduced live snapshot starvation under sustained world updates

The real `SessionEventOutbox` reproduces indefinite avatar and permission
snapshot starvation when entity edits continue between slow renderer
acknowledgments. Replacing an unsent snapshot by removing and appending it moves
that snapshot behind each new entity edit. The queue stays bounded while the
renderer receives entity edits exclusively. The new public-behavior regression
`tests/session-event-fairness.test.ts` fails both live-delivery cases against the
unchanged implementation; its deletion/lifecycle ordering control passes. The
ignored fail-before log has SHA-256
`c94deb9276f1c3ef74d0309fc4f71f272b5feaf7d1c372c0002c832bc9fe6960`.

Independent review confirms the scheduling defect. Direct-d's first entity
service channel receives 50,765 entity datagrams while its main thread has long
tasks exceeding a second. These observations support the busy-renderer workload;
they do not directly record event acknowledgments or prove this defect caused
the earlier motion failure. The scoped correction will retain an unsent
snapshot's queue position only within the same-generation independent
entity-edit/avatar/permission segment. Real deletion, full snapshot and session
lifecycle barriers retain the existing order. The quiet motion probe continues
to use the original production worker before this change is built.

## Quiet native motion passes; fairness repair production freeze

`avatar-motion-probe-chrome-20261003-a` ends naturally at 04:02:19.936 UTC,
exit code 0 and empty owned browser registry, after 12.372 seconds. All three
diagnostic steps pass on the original production worker. The genuine native
negative-Z operation advances observer sequence 371 to 373 with measured
Z displacement -0.949890 m after settling. Raw received global position, the
actual outgoing worker avatar event and the real facade callback each contain
the same newer position after application, with zero horizontal displacement
error. Strict restore advances 373 to 375 and returns exactly to the original
X/Z. There are no primary/cleanup failures, page exceptions or model/image
requests. Complete result SHA-256:
`b13bb5cea7769bac515261f176296470f6ec404fdbf261467117a25ec844d23f`.
This establishes the normal quiet position pipeline, not the loaded-body or
full-world acceptance criterion. Both attempted supplemental AvatarMixer
samplers occur outside this short admitted window; they are not motion evidence.

The reviewed `SessionEventOutbox` correction now keeps live snapshots in their
existing unsent slot only when all following queued events are independent
same-generation entity edits/avatar/permission snapshots. A real deletion,
full snapshot, other generation or lifecycle event retains the previous
discard/append behavior. Posted messages and the 32-event/65,536-entity bounds
are unchanged. All three new regressions and all 13 existing worker-runtime
checks pass without changing their expectations. Pass-after log SHA-256:
`2422acf59694c407ce61ef30e858cf112ddd0abf7a46491837090ee406600dd0`.

The complete browser suite passes 267/267, zero failures/skips, in 2.7666 s.
Strict TypeScript and production build pass; Vite completes in 2.40 s.
Renderer provenance remains 87 exact/8 adapted and SDK provenance remains
115 exact/32 adapted/6 omitted. The actual compiled C++ protocol table and
signature match using the prepared Conan GLM include directory; the initial
host-only invocation lacks system GLM headers and is retained as a prerequisite
failure, not a product protocol mismatch.

Final browser artifacts for the next real journey:

- Main `index-iFELnfez.js`: `5b75c358253e392439f12fc6d717bd080b16007c69a42a7f6d3f3928721da240`.
- Worker `session-worker-CCRrMTDi.js`: `85dee54c1d3a1edc91d94909085891d5930f658d8109e059f679f651e931ebec`.
- Unchanged worklet: `966ccb298ddb5f3339442a8989ee11238c34987b1f0227b9ef6ac14e53e71931`.
- Ignored production freeze record: `0e5771414ea75b0a351fa2fca0b8a71bee50d06c9fc9671983a565b9dd63157f`.

Seventeen public temporary-file native-build evidence contracts pass. They
cover candidate inventory/symlinks, build locking, late and prewrite source
races, exact six-program evidence, zero checks/skips/JUnit failures, and keeping
the original immutable manifest when compiled bytes are identical. This
helper coverage does not execute native services or a compiler. Final native
ON build/test/source qualification is in progress before the new full-world
journey; default-OFF compatibility and equal-quality benchmarks remain open.

## Final source-bound native runtime and complete Chrome journey

The final ON build exits successfully and its six selected CTests pass in
1.92 s, with Qt totals 19/6/9/8/7/7 passed, zero failures/skips and the unchanged
45-second per-program bound. The observed source fingerprint covers 2,662
native source/configuration files. This separate build record preserves earlier
immutable manifests rather than rewriting their provenance.

| Final native evidence | SHA-256 |
| --- | --- |
| Native source fingerprint | `191ba56a74169a1cc4b2ecf6a8fd2bd2eb5fa9df155a9883393c1ed8367b0dec` |
| Executed immutable runtime | `b24fe1e9aa4268574864e3d359a862588917d1876053f044af81e1ef8737efe0` |
| Immutable snapshot manifest | `fae3a25703c7ea2ca6d307aa1dd95bcf3334d1d408543fad0045822cd3f4167e` |
| Final build/source/test qualification | `a7c9fee9a014912f5cf3961a259156e9832bee36dce14f4a4b3cbf29a09d43cd` |
| Actual build log | `5de3ab9fdcf841f233d4cd10093716cb049820c9b28bbe3982e886140654cbc2` |
| Six-program test log | `b353e2305c470e04c8a0d43ac04ca43713deef68a2802788ac700288eebec5d1` |
| Exact JUnit inventory | `cc91614c69bb50db6bee2748187ed01c6905f0d4a8166a99b67f9b17cb3e06ea` |
| Fresh actual native visitor qualification | `32af0cc2d36180180f945d0ab68c636905e3fa796d66fd44abc2d9b7f579852e` |
| Stable six-service readiness | `8c4fee602887f52a1ec8cc4a5032054602004f0e1d7f5d2b61057dc64240d9a0` |

The first packaged native launch exits 139 before qualifying its spawn/rig;
that negative is retained. An unchanged supervised native-only retry actually
loads the ordinary domain Hub spawn, 53 nearby entities/34 ATP view-subset
models, 69 native joints, two loaded rig meshes and the real HTTPS bridge.
Same-launch Qt requests match the recorded FST/FBX bytes and all six current
native service endpoints are observed. Only after that ordinary proof is the
separate native-only three-metre setup applied. The new source-v2 one-metre
motion trial is unused when the complete journey starts. This successful retry
does not diagnose or erase the earlier startup crash.

```bash
python3 browser-direct-client/e2e/run.py --mode direct --audio \
  --run-id direct-chrome-20261003-e --timeout 180
```

This unchanged 25-criterion journey runs from 04:39:56.029 to 04:51:55.594 UTC,
ends naturally in 11 m 59.565 s with exit 0, **25/25 passed**, zero uncaught
page/shader errors and an empty browser registry. It executes the final main,
worker and worklet hashes recorded above. The complete result is ignored
`build/browser-direct/e2e/direct-chrome-20261003-e/results.json`, SHA-256
`2c3b0f9afaf351601cbe9d9920d2c44ca068691333bcba69063eaa8224065dab`;
bundle manifest `132ad8a91a185e135c1bb5da4a9f79a490a623d6ed31f84a4a7b2e9abe296132`.
The earlier 24/25 direct-d failure remains historical negative evidence.

Actual native observer sequence 446 to 449 records horizontal displacement
(-0.001602, -0.950256) m. The loaded main-view body moves
(-0.001602, -0.949890) m with ten actual rig draws and no body-sample eviction.
The browser is not teleported. At the first recorded moved pipeline snapshot,
raw native positions increase 494 to 506, actual worker-post samples 142 to
145 and actual page Worker-message observations 142 to 145; all contain a
newer moved position. Page-message observation is not a facade-callback claim.
Native observer sequences are not wire packet sequences. Strict restore
475 to 477 returns the exact original horizontal position with no retained
primary or cleanup failure. The root reviewer views both actual before/moved
PNGs and confirms an upright textured rig at its changed location.

| Actual synthetic direction | Captured 48 kHz frames | RMS | Target amplitude | Other tone amplitude | PCM SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| Native 523.25 Hz to Chrome output | 383,506 | 0.026315 | 0.009484 | 0.00004655 | `95ede8e37fb389b82e0109bed07393cbc633bcc8ece0fb6595aacf8cf213e1f8` |
| Chrome 659.25 Hz capture to native output | 383,040 | 0.058156 | 0.006005 | 0.00013436 | `53c5a034b34bef4d29bfb4e927a62e385bba60336d6bd2132fb4a169860954c3` |

Browser capture/sent frames increase from 0 to 995 with no microphone-frame
drops. Its Audio-app action enables real `getUserMedia` against the own virtual
Pulse input after an automation permission grant. Neither direction is physical
speech or a stock browser-UI permission-decision test. Leaving stops capture
and closes every real peer/transferred worker channel; reconnect uses fresh
channels. The local Snapshot app saves an actual 1,280 by 800 PNG.

The bounded AssetServer trace covers exactly 04:40:16.453 to 04:43:16.452 UTC:
180 admitted-browser samples, RTT 0–5 ms and observed peak 10.3285 Mbit/s.
It does not cover later movement/audio or the entire journey. After END,
cleanup records one native Agent, zero other Agents, two AssetServer peers and
zero post-END RTC failed-write records. The runtime's lifetime count is 18,
which is not a zero-during-run claim. Ignored evidence hashes:

- Native motion/strict restore: `deb5351a448be8f20b9b8e10371e9746d1ef3f126fc6265f427995308d0aa3d4`.
- Exact three-minute asset trace: `eef652c1ab825b02fe97b22c0d6d5f2a84f4e279f0d9fa4ad88cc9ef9fe5f8ef`.
- Asset summary: `c40b3dca869b77bd43c3be313d3e3fd6d7894f72dcad4bc2e6575bee0a2a2be0`.
- Cleanup seal: `4a895f2b77962de35a344e57a0d60aeeaba008e8707279821c61221f37e3a3e1`.
- Visible native PNG: `8bb24ab8e17c02183bf81124731e4d880f9bb669d916e3f5b656cfd117c58016`.
- Moved native PNG: `c5b619a9fa46caf5de6aa4626603a203084f7d9c3b2b9a2856c0b1b8338604b3`.

## Four actual equal-quality loading comparisons

```bash
python3 browser-direct-client/e2e/run.py --mode benchmark \
  --run-id benchmark-chrome-20261003-a --timeout 240
```

The four fresh Chrome 153 profiles run in ON/OFF/OFF/ON order with the same
production assets, native runtime, scene, graphics, viewport and restored
native participant. Only decoded-image sharing changes. Each admission/first
ready/full-scene phase shares one absolute 240-second scene deadline, within
the existing 285-second complete-case and 1,200-second batch bounds. No CPU
build, source/service mutation, extra lab sampler or permission test overlaps
these measurements. All four cases pass and naturally end at 05:10:09.214 UTC;
the browser registry is empty. Ignored complete result SHA-256:
`4cce98e7975664333f9754dbcfd49673db81d14e905eaa6601bb92ccfd5a8b9d`.

| Fresh case | Sharing | Admission (s) | First render ready (s) | All 55 models/maps ready (s) | Completed Image instances | Completed-image pixels |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | ON | 3.091 | 6.415 | 174.104 | 42 | 39,342,080 |
| 2 | OFF | 2.440 | 7.944 | 169.921 | 104 | 60,989,440 |
| 3 | OFF | 3.080 | 7.568 | 173.220 | 104 | 60,989,440 |
| 4 | ON | 2.485 | 7.634 | 175.432 | 42 | 39,342,080 |

Identical browser observers show 59.6% fewer completed Image instances and
35.5% fewer completed-image pixels. Summed src-to-load/error event duration
averages 99.633 s versus 160.835 s, 38.1% lower. That aggregate includes waiting,
implicit decoding and main-thread event dispatch; it is neither decoder CPU
time nor the complete-scene critical path. The baseline has zero explicit
`Image.decode()` calls, which does not mean zero implicit browser decoding.

Complete-scene time averages **174.768 s ON versus 171.570 s OFF**, 1.86%
slower in this four-case sample: no complete-load speedup is established.
First-ready mean is 7.024 versus 7.756 s (9.4% lower), but the second pair's
direction reverses, so consistent startup improvement is not established.
Software cadence is 1.32 versus 1.34 fps, with roughly 975 versus 992 ms p95
frame intervals. This is not smooth navigation or hardware GPU evidence.

Both pairs preserve source/served scene and asset hashes, the same native
session and exactly unchanged native position. Browser horizontal pose
distances are 0.000208 and 0.000302 m. All 55 geometries/maps complete, exactly
the same original PSD warning remains, sky draws are ready and no page/shader
error occurs. The root reviewer views all four actual world PNGs: the bridge,
stone, tree and textured upright native body retain the same visible quality.
Actual clouds and native articulation remain live. Exact pixels differ;
32 by 20 sample-grid mean absolute RGB differences are 9.788 and 10.771.
Functional pair success is not a pixel-equivalence claim. Full native shader
parity and a separate runtime sampler table are not established by this test.

The measured improvement is less repeated image loading at preserved visible
quality. Complete-load latency and smooth hardware movement remain open; the
recorded timing scopes are being assessed before any further performance change.

## Actual Chrome microphone permission and capture lifecycle

The isolated permission test imports the unchanged production `BrowserAudio`
component. It joins no domain and renders no World. Every case uses a fresh
owned Chrome profile on private display 104, with hardware devices absent and
only the own virtual Pulse remap selected. No permission API override, fake
media device or physical input is used. The stock popup is captured only after
checking the actual process executable/profile/start ticks/driver ancestry,
UTF-8 title, unique viewable window, complete root-screen bounds and absence of
foreign overlapping windows. The root reviewer also views the actual popup.
Reviewed coordinates drive real XTest events inside that same checked window.

```bash
python3 browser-direct-client/e2e/run.py --mode permission-probe \
  --run-id permission-probe-chrome-20261003-g
```

The corrected two-case test naturally ends at 05:36:11.287 UTC in 49.933 s,
exit 0, **2/2 passed**, zero page errors and an empty browser registry:

- Actual **Never allow**: default `prompt` becomes `denied`, native
  `getUserMedia` returns `NotAllowedError`, no stream exists, and capture stays
  muted. The trusted Stop action completes disposal.
- A separate fresh profile's actual **Allow this time**: default `prompt`
  becomes `granted`, `BrowserAudio` enables one real live audio track from the
  own virtual source. Eleven capture callbacks each carry the exact 480-byte
  native 24 kHz PCM frame. The actual AudioContext runs at 44.1 kHz. Trusted
  Stop ends every returned track, mutes capture, disposes worklet/context and
  prevents later callbacks.

Ignored complete result SHA-256:
`66b1a784d9c637a9fa017cf5d7d4e7834ab88a36838a41cc2c56b01d5d34b545`;
filtered summary `2373a2ec18c6de3291e508d9cbc6e6fe55331e392b0697c8f47f1641866933d6`.
Both fresh pre-decision popup PNGs have SHA-256
`a8d6dc09b28f65f63fe2874204732c8fe5c96d08c4e0b440c0cece681deba808`.
Main/worker/worklet production hashes remain unchanged. This is actual browser
consent and virtual-source capture evidence, not physical speech or native
voice evidence; the separate complete direct-e test proves synthetic transport.

All six earlier attempts remain negative. The first failures identify Chrome's
joined Linux process title, Python-Xlib's legacy STRING title lookup versus
Chrome's UTF8_STRING property, and a browser window larger than the actual
1,024 by 768 private root. The helper reads a bounded typed UTF-8 title and
refuses clipped capture/input; only this diagnostic's viewport becomes
900 by 600, while world-test viewports remain 1,280 by 800. In direct
permission-f, real deny passes and actual UI allow becomes granted, but a
premature asynchronous polling assertion cancels the still-requesting capture.
The corrected driver atomically awaits real state under one absolute deadline.
Ten ownership/window/bounds contracts and three delayed-state/error/deadline
regressions pass. Browser CI includes the Python contracts with Xlib/Pillow
prerequisites; these contracts do not substitute for the actual g run.

## Remaining loading investigation

The completed benchmark cannot assign its LongTasks to GPU work: CPU-frame,
render-CPU, upload and GPU diagnostics were disabled. Main FBX parse and graphics
submission each total about two seconds, while LongTasks total about 180 seconds.
The larger shader/FBX preparation clocks include overlapping asynchronous waits.
The current ATP request route is ServiceWorker to main page to session worker;
its transferred reply port already bypasses the page. Small FST/JSON resources
still take approximately 1.4–1.6 s amid roughly 750 ms rendered-frame intervals.
This supports measuring the main-page dispatch stage, not claiming causation.
A bounded passive one-profile real-scene probe runs after the separate
default-OFF CPU build naturally ends, before any further loader change.
Its helper and context contracts pass 21 tests, including actual transferable
ports, preserved native arguments/results/promises/errors, salted private
correlation, clock availability, repeated-key ambiguity and bounded observation.
The first actual attempt stops before Join in 2.523 s because its exact asset
controller is still `activating`; no admission or loading evidence is claimed.
Ignored negative result SHA-256:
`6f9fc2103075ea67c56e42c1efbc23a9e0121d8bb22abec1ac082e6512c5473e`.
The preparation now awaits the same worker's actual activation within one
original 10 s deadline. Its delayed-activation, expiry and redundancy regressions
pass, and the next isolated run retains the unchanged production/native scene.

## Completed default-OFF native compatibility build

The separate fresh offline build omits the feature option and records CMake's
actual default `OVERTE_BROWSER_TRANSPORT:BOOL=OFF`. It uses the same digest-pinned
dependency image and source fingerprint
`191ba56a74169a1cc4b2ecf6a8fd2bd2eb5fa9df155a9883393c1ed8367b0dec`,
with its own output/cache and no libdatachannel prefix. The real domain and
assignment builds naturally end at 05:50:51 UTC, exit 0, after 1,470.646 s.
The exact three selected generic-policy CTests naturally end at 05:50:52 UTC,
exit 0, with Qt totals **8/7/7**, zero failures/skips. This is a bounded test
subset, not all five normal networking programs, the full generic native lane
or Interface.

All 739 generated compile entries, expanded domain/assignment/networking link
commands, ELF `NEEDED` entries and resolved dependencies exclude DataChannels.
The ordinary pinned shared WebRTC audio-processing library remains an actual
linker input; the server ELF lists omit that unused input. No audio-disable flag,
forced dependency, source change or test exclusion is introduced. Inspection
expands Ninja response-file commands read-only; it does not rerun a successful
compiler/test phase. The first configure's missing local generated tool-directory
file and the earlier inspection assumption remain separate negative evidence.
Source fingerprint and the live `b24` runtime/manifest match before and after.

Ignored qualification `lab/runtime/default-off-build-qualification.json`:
`9c4cad23690cb687bfd70913fe57c30f0bfc622e414ea9d7d714ca2727152917`.
Actual build log: `0d16be742c0f9e5edbaf500269f7962b1bb27edd749b087f9f03cbbb2800b8c6`.
JUnit: `389a3838daab66c50dccca0f5b001b1d626b19b548f95c60279752a3b9a9e671`.

## Chrome passive asset-dispatch diagnosis

```bash
python3 browser-direct-client/e2e/run.py --mode asset-dispatch-probe \
  --run-id asset-dispatch-probe-chrome-20261003-c --timeout 240
```

The actual Chrome run naturally ends from 06:10:38.311 to 06:14:30.274 UTC,
exit 0, 231.963 s, with an empty browser registry. It preserves the previous
main/worker/worklet distribution, the `b24` native runtime, scene/asset hashes,
default image sharing and 1,280 by 800 viewport. All 83 entities, 55 model
geometries/available maps, the exact known original PSD warning and contained
4,096 by 2,048 Zone skybox pass. Join-to-full-model readiness is 191.5134 s;
this diagnostic includes observation overhead and is not a benchmark arm.
No microphone, permission, native motion or hardware GPU test occurs.

All 158 actual requests have the correlated three-realm boundaries, valid
epoch/wall clocks and no ambiguous keys, missing stages or observation losses.
The useful event-arrival intervals are:

| Observed stage | Median | p95 |
| --- | ---: | ---: |
| Asset ServiceWorker to page | 1,450.20 ms | 2,373.10 ms |
| Page forwarding | 0 ms at timer precision | 0.20 ms |
| Page to native session worker | 0.70 ms | 7.60 ms |
| Native mapping/get/hash resolution wait | 22.00 ms | 1,045.60 ms |
| Session-worker reply directly to asset ServiceWorker | 2.90 ms | 19.20 ms |

The main-page stage is positive for every request, minimum 366.20 ms. FST and
JSON means are respectively 1,530.59/1,570.94 ms in that stage versus 8.75/14.19
ms for native mapping/get/hash resolution. The stage includes dispatch waiting,
not isolated CPU or GPU execution. Concurrent phase sums overlap and cannot be
subtracted from the 191.5134 s scene interval.

Correlation is explicitly **partial**: the late passive reply listener produces
79 negative reply-to-response intervals and 79 timer-quantized zero intervals.
The existing `onmessage` resolves the fetch before that later listener; its
promise continuation may construct the Response first. Response-construction
cost is therefore **unavailable**, including the nominal zero samples. The
other seven stage intervals remain valid for all 158 requests. Every FetchEvent
uses the observed `respondWith` fallback; readiness alone was not request proof.
Two failed network requests are recorded; page/shader errors remain zero.

Natural leave reports disconnected, closed peers and muted capture; all three
observer hooks restore. Complete result SHA-256:
`c32a6c3b75ff735d2e12736914f8acee3712515eeaf794ebc377ad2ebf7fae33`.
Filtered aggregate:
`3d47462a60057d176a033911d35ed9e22a668ba02504c6aaa348485f7bd09b22`.
Post-END cleanup:
`f62ab4bcaca3ff17c187ee9a209d6053666dc1a82065969ecf828e9aab3e81ac`;
same native participant, no extra visitors, two AssetServer peers and zero
post-END failed RTC writes. The runtime-lifetime counter is 48; no zero-in-run
claim is made. The earlier direct-e AssetServer trace does not cover this probe.

The a/b no-Join negatives remain. Attempt b passes exact active-controller and
three-realm readiness but stops during the ordinary asynchronous pre-connect
audio initialization. Its result is
`2bf441207e8f7210c3e28259285ef7d5185deb7be108d085ed588b34b6ad4876`;
all request intervals are unavailable. The repaired test permits initial idle
only before real admission and still fails errors and post-admission loss under
one original common deadline. The focused helper/context/deadline suite passes
23 cases. These test-only changes do not modify production byte hashes.

The next implementation removes only the measured page request hop. It must
bind the actual requesting tab and current generation, retain native asset
validation and per-request reply ports, bound registrations/pending work, and
revoke stale bindings/results on leave, reconnect, failure and disposal. Loading
gain remains pending a matched direct/page/page/direct real-scene comparison.


## Direct local asset port: source freeze (2026-10-03)

The implementation replaces only the ServiceWorker-to-page request hop. The
ServiceWorker and actual session worker exchange an acknowledged MessagePort
bound to the real WindowClient, session generation, registration identity and
monotonic sequence. Each fetch retains its original direct reply port. Native
admission, ATP mapping/get/hash/size checks and structured cloning of shared
native results are unchanged. `assetDispatch=page` selects the explicit original
request baseline for the forthcoming same-bundle comparison; there is no silent
fallback. Safe route counters expose mode/readiness/counts only.

Bounds are 128 pending requests per session, 512 across the active ServiceWorker,
64 tab registrations, five seconds for route preparation and two seconds for
retirement. Leave/error/disposal immediately revoke native/reply-port authority.
Delayed registrations, stale completions/revokes and another tab cannot replace
or borrow a fresh session. Only a specifically typed retirement acknowledgment
timeout can finish local leave with `assetRouteAcknowledged: false`; other
retirement failures and peer-broker reset errors remain rejected. Every new
native connect still requires a positively acknowledged fresh owned route.
This lets the first explicit reconnect recover after Chrome discards an idle
ServiceWorker context, without pretending that its missing old acknowledgment
was received. Indefinite ServiceWorker residency is not claimed.

Source review found two additional retry defects. A failed preparation now
clears only its captured cached promise, and a recoverable join error cannot
permanently reject the owned worker's bootstrap promise. Terminal bootstrap
failure/disposal retains its normal terminal behavior. Tests also cover
leave/disposal while actual readiness remains pending.

The focused real-MessagePort/native-boundary suite passes **45/45**, zero
failures/skips, in 4.96 s. Strict TypeScript, ServiceWorker syntax and scoped
whitespace checks pass. Command:

```sh
cd browser-direct-client
node node_modules/tsx/dist/cli.mjs --test tests/asset-routing.test.ts tests/asset-worker-bridge.test.ts tests/worker-direct-session.test.ts tests/session-worker-runtime.test.ts
```

The nine production files have aggregate SHA-256
`8ac55d869a6b7f5d780675a85dc5327ac80c79f0f26a8eb802df0c660dcc250f`;
those files plus three owned test files have aggregate
`aeca1cacaddb0664c4775f8ab14cd00dc6474bd5d76b89c39aa4b79623f9fcf9`.
The aggregate hashes sorted client-relative paths, each followed by NUL, its
lowercase file SHA-256 and a newline. The primary agent independently reproduces
both digests and reviews the production and lifecycle-test changes. Native
source/runtime remain the qualified `191ba56a...`/`b24fe1e9...` checkpoint.

The consolidated suite, production artifact, fresh actual interoperability run
and four-arm loading comparison are pending. Earlier `direct-e` and loading
results remain bound to their original production bundle; they do not qualify
this new route.


## Consolidated route build and repository checks (2026-10-03)

The primary agent runs the complete source-frozen browser suite: **320 passed**,
zero failed/cancelled/skipped, 6.564 s including the runner. Renderer provenance
passes for 87 exact files and eight hash-bound adaptations; SDK provenance passes
for 115 exact inputs, 32 documented adaptations and six explicit omissions.
The native C++ protocol generator/check passes with the prepared GLM include
path. Strict TypeScript and the production build pass in 6.333 s. No native,
renderer, asset bytes, image quality or worklet changes were introduced for the
new local request route.

Current production artifacts:

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `assets/index-CCEFI6gS.js` | 976407 | `62e925e106ac4a351a09f8876658798f15d38f4be06e85114d5ee76f677760fc` |
| `assets/session-worker-n-ijwJbM.js` | 447111 | `fc8d16188f602a1b969de78425086cd60ce8644e30baa3c90f8add9fda6df709` |
| `assets/audio-worklet-Dh5YJhbv.js` | 9753 | `966ccb298ddb5f3339442a8989ee11238c34987b1f0227b9ef6ac14e53e71931` |
| `asset-worker.js` | 13175 | `53096db2252489d6319b2bb9ef4c3482b9f5104b4d9b78d4fa6ac5b52e876bd6` |

The complete 40-file artifact manifest has SHA-256
`b9e763d1dcff0f2ce8d99bda8a05610cbcc236e41e5a5f1d48026c0c476c3d4b`.
The private production freeze has SHA-256
`f9960d6269e4a89ed9c8b5364cb3fa44846aa0a117824a681188a68e8a0fd6c6`.
The supplementary completed-check record has SHA-256
`371999c39c32fb216ac34bf46d713d8b28dc201cad3b5ff56a41783489f38d8a`.
All reside under ignored `build/browser-direct/checks/20261003-direct-asset-port/`.

All CI helper contracts pass independently: launcher 8, native host actions 7,
fake-file native build evidence 17 and Chrome permission UI 10. These do not
open a browser, native service, physical microphone or hardware graphics context.
The changed renderer-free asset diagnostic builds successfully and now uses the
actual dedicated session worker, registered asset route and transferred-channel
observer. It observes actual versus explicitly requested ATP HTTP requests;
it does not assert zero automatic requests from an invented constant. Its
native binary-byte integrity, 35-second request observation bound and full
actual worker-channel cleanup criteria remain required.

The refreshed required repository command passes **34 suites**, zero failures,
in 214.279 s including its runner:

```sh
python3 tests/run-project-tests.py --profile quick --timeout 240
git diff --check
```

Exact browser/protocol/provenance/helper/build commands are the commands in
`BUILD.md`, the CI workflow and `e2e/README.md`; their retained individual log
hashes are in the completed-check record. Key log SHA-256 values:

- Browser suite: `fc0706566f3507691bf6e2943500c1941144e1b02e8bd9b251f3f00782ce5428`.
- Production build: `fd49d3705c06e7088f629001264eac2f52204ed3c6dc27866ce946a8c953d17c`.
- Repository quick: `d0eec3248159f1b17d44b38fa6feb67b3707e619cf4abb89cb92987e81bdfe3c`.
- Renderer-free diagnostic build: `09ad0be68bb94a9c280214c1b7c3b96f9f35ad51e074673f750c1b224b2d089f`.

The 07:04:42 UTC read-only resource refresh retains one physical ALSA input with
both microphone ports and the line port explicitly unavailable. Its persisted
state is suspended; an earlier transient running state did not make a port
available and did not prove speech capture. Nine verified foreign registered or
descendant processes are inspected. Two DRM descriptors belong to two foreign
Xvfb processes; no NVIDIA descriptors are present. Descriptor ownership proves
access, not active graphics workload or a shared exclusive window. No physical
input, hardware context, route or foreign process was changed. Private readiness
SHA-256: `eaa99cc6a7ae1251c93b6a0c87fa6b611230c68091d4434004e4e8ca09de0698`.
Physical speech and hardware fluidity remain unproved.

All CPU checks/builds have ended, and the browser process registry is empty.
The primary agent releases only the owned native visitor for archive/restart
and fresh ordinary-spawn/assets/endpoint qualification. The new source-bound
unused motion trial must exist before the actual interoperability journey; that
journey and the four-arm route comparison remain pending.


## Fresh native actor and current route asset diagnosis (2026-10-03)

The owned native visitor is restarted only after all CPU builds/checks finish.
The previous consumed/restored actor's 22-file history is retained with archive
manifest SHA-256 `167fbb9f276dd1d74ed441f2fdb18d7e818a597db5cc533428eec2f25ab48d14`.
The new actor/session differs and has an unused guarded version-2 −Z one-metre
motion/strict-restore trial. Observer source remains `d45e18cd...`; immutable
runtime `b24fe1e9...`, completed native source/test attestation `191ba56a...`,
DS/AC identities, scene, assets, TLS fixture, displays and Pulse routes remain
unchanged. No server rebuild, sampler, native trial or hardware context is used
during requalification.

The initial new launch connects and loads genuine world/assets but remains at
the origin; that negative is retained. Its single ordinary `/` lookup retry
then yields actual Hub pose `(155.0840, −97.3865, −397.3139)` before any explicit
placement. Separate three-metre native avatar placement follows that observation.
The current native view records 64 entities/45 loaded ATP models, the genuine
HTTPS bridge and 69-joint/two-mesh mannequin. These are view counts, not browser
full-scene counts. Actual current-launch Qt HTTPS FST/FBX hashes and all six
services' real native UDP endpoints qualify before trial publication. No
exit-139 startup occurs in this launch.

- Fresh visitor qualification SHA-256: `5407f45ca510d7a936b79dd73551c1304e557188f10703d96b4d4ef2da75e7f9`.
- Fresh motion readiness SHA-256: `c15e9a4ab21953b88bbb01d6d5090fdcc568fa37074f15d4666bce156dd034fd`.
- Fixture source freeze SHA-256: `56de08b903cfb328efc4780fa70a207499d3b11bd42b562620b339d32976b118`.
- Safe current-process/source/unused-trial proof SHA-256: `433fa0d3915d52a4d91604ec4a05abae88a5105e23039d98b807646c15283a89`.

The separately built current worker-based renderer-free diagnostic
`asset-probe-chrome-20261003-new-route-a` passes **6/6** naturally, from
07:25:00.127 to 07:25:09.445 UTC (**9.318 s**): real join, no automatic scene
asset requests, both actual native serial asset transfers, actual worker-channel
closure and no uncaught exceptions. The EXR is 4,143,539 bytes/2,187.8 ms; the
FBX is 1,824,496 bytes/1,136.5 ms. Both return HTTP 200 and the exact unchanged
source/served hashes. Actual route counters advance direct requests 1→2,
page requests stay zero, the direct route is ready and rejection/registration
failure/pending counters remain zero. The HTTP ledger observes exactly the two
explicit requests. No renderer, motion, microphone or physical-device test is
performed by this diagnostic. It does not establish scene-loading speedup.

Command:

```sh
python3 browser-direct-client/e2e/run.py --mode asset-probe --run-id asset-probe-chrome-20261003-new-route-a --timeout 55
```

Result SHA-256: `224e7c076953ca778f1de0707bf7e03e45daa9dc56990048139c1c0fd509e431`.
Filtered transfer-summary SHA-256:
`bc2a325c5d2b0d06100a9105b28b700bde7bbeb2bbc801e1daa52dcec49f6201`.
The complete production `direct-chrome-20261003-f --audio --timeout 180`
journey has now started on the separately frozen current production artifact.
Its final result and the subsequent four-arm route comparison remain pending.

## Current direct-route journey and interrupted host launcher (2026-10-03)

`direct-chrome-20261003-f` completes from 07:26:51.434 to 07:38:15.488 UTC
(11 min 24.054 s) on the current 40-file production manifest
`b9e763d1dcff0f2ce8d99bda8a05610cbcc236e41e5a5f1d48026c0c476c3d4b`.
Its result is **failed: 24/25 criteria pass**. The trusted keyboard criterion
correctly rejects an independent host identity proof older than the unchanged
three-second limit. The host launcher is no longer live while its separately
registered browser driver continues; the command session reports exit143.
The last host proof is at 07:34:32.175 UTC. The exact external termination
cause is not established. This is not a successful complete qualification,
and no replacement proof is written to rescue the interrupted run.

All 55 real model geometries and available textures, native spawn, local tablet,
source-byte integrity, actual skybox and HTTPS draws pass. The loaded remote
body follows a new native move: native sequence444→448, native displacement
`(0.0013733, −0.9962769)` metres in X/Z, actual body displacement
`(0.0013733, −0.9960632)` and twelve real rig draws. The original 0.25-metre
horizontal bound holds. Strict native restore advances sequence472→474;
no motion/restore error or browser teleport is recorded. Both actual before/
after body PNGs are inspected. The actual direct route is ready, page requests
stay zero, and registration/rejection counters remain zero.

Both synthetic audio criteria pass independently on the current bundle:

- Native523.25 Hz → actual Chrome output: 383,841 frames at48 kHz,
  RMS0.0248601 and matching-frequency amplitude0.0119629.
- Chrome659.25 Hz → actual native output: 382,080 frames at48 kHz,
  RMS0.0645561 and matching-frequency amplitude0.0144263. Actual browser
  capture/sent frames advance0→854 with zero microphone-frame drops.

Jump/landing, source picking, snapshot, leave, fresh reconnect and explicit
unavailable-domain cleanup also pass. Page/shader error counts are zero.
Physical speech and hardware rendering are still unqualified.

After the driver writes its natural final result, the exact worktree-owned
`python3 browser-direct-client/e2e/run.py --stop` command exits0, reports zero
remaining owned browser processes and leaves the actual
`lab/runtime/browser-tests.json` registry empty. The failed result and stale
host proof remain unchanged. The native actor is still connected and its
one-shot trial is consumed/restored; a repeat motion journey requires a new
qualified launch. Graceful launcher interruption and a bounded independent
launcher are being addressed before another long run.

Result SHA-256:
`ab802a5d6a986c58e6bc74f2136102e72e446b93d85de34921bfe45912447bc3`.
Filtered outcome/cleanup-summary SHA-256:
`73f5a50f77834f40d233bea53039d898efe1e6495e57fa23ba6d9d6d0b13111b`.
The four-profile direct/page/page/direct loading comparison remains pending.

## Launcher cleanup and public visitor qualification (2026-10-03)

The launcher now routes the first SIGTERM/SIGHUP through its existing bounded
host compensation and exact-identity process cleanup. Repeated signals during
that cleanup cannot leave the registered driver/children running; previous
handlers are restored afterward. Two actual-owned-process regressions fail
with the earlier default signal behavior and pass with this change. They
also verify that a deliberately incorrect start tick prevents an outsider
signal, and that the registry and lock are released. The original host
freshness limit, native motion guards and browser time budgets are unchanged.
Root verification passes **10/10 launcher** and **7/7 host-action** tests.

- Launcher source SHA-256: `154e552aab6a778af93538e35e4755b33112333bb3a9124543998b78c27e31ad`.
- Interruption-regression source SHA-256: `0792716d1f201ded69c52d249481ddd594a362fd9282b46c8f2c2bfc2423ed28`.
- Root launcher-check log SHA-256: `7c134b8949f4f2d77acac8f7a6b3158ee033c9b51c88b4a3eff814b2caee3376`.
- Root host-action-check log SHA-256: `49a04637fd0b91e135e10b5953be3e753f3867d3f47a3a1b8fd414c6569ef00a`.

An ignored local supervisor starts the same public Chrome command in its own
session, records exact launcher/supervisor identity and source, and retains
the original 1,200-second driver bound for the four-profile comparison. Its
outer watchdog accounts for bounded server setup and cleanup; it does not
extend any scene, case or driver test deadline. The new
`benchmark-asset-route-chrome-20261003-a` starts at 07:47:19.431 UTC. Other
builds, helper tests, samplers, audio and UI diagnostics are held while it runs.
Final benchmark evidence is still pending.

Public native qualification now writes the observer version/source fields
required by the browser launcher after validating the actual started source,
fresh version-2 sample, exact current process and unused trial. Previously,
the documented public helper omitted these required fields, so a private
post-processing step was needed. The existing real ordinary-spawn, separate
placement, six-service and same-launch Qt asset-hash checks remain required.
Seven focused temporary-observation/owned-process regressions pass before
the benchmark starts. They exercise the public CLI writer and actual browser
start guard; they are not native-world interoperability evidence. CI includes
the new regression command. A new actual native launch will exercise this
public workflow after the benchmark ends.

Qualifier source SHA-256:
`9c575f335dffb08a28de842e0a26d83c18e77854aed6b2a117c53923802f8e19`.
Regression source SHA-256:
`af8c9c3a8185b36f1882ed203c60ba27eb543a685093520c347ff8fc019b93f0`.
LAB instructions now include the public source-before → successful build →
six verbose/JUnit tests → candidate → build-qualification chain through the
existing shipped functions. A source inventory alone is explicitly not a
compiler attestation. Completed build/live/visitor records remain separate;
earlier artifacts and negatives remain unchanged.

## Controlled direct asset-route comparison (2026-10-03)

`benchmark-asset-route-chrome-20261003-a` passes **4/4** from 07:47:19.431
to 08:01:53.772 UTC (874.341 s), naturally inside the original common scene,
case and batch bounds. Four fresh Chrome profiles use one frozen production
artifact in direct/page/page/direct order; decoded-image sharing stays ON.
No build, helper test, sampler, motion, extra UI or audio diagnostic runs during
the comparison. The actual native actor/session stays the same and stationary.

| Case | Actual request route | Admission (s) | First rendered model (s) | Complete scene (s) |
| --- | --- | ---: | ---: | ---: |
| 1 | Direct worker | 2.2724 | 5.7567 | 129.1717 |
| 2 | Page forwarding | 2.2022 | 7.4157 | 183.6774 |
| 3 | Page forwarding | 2.9570 | 6.5846 | 173.9224 |
| 4 | Direct worker | 3.0046 | 7.8680 | 123.0615 |

Complete-scene means are **126.1166 s direct versus 178.7999 s page**:
**52.6833 s / 29.46% shorter** in these four software-rendered observations.
The individual paired reductions are 29.67% and 29.24%. First-render direction
varies between pairs, so this is a full-scene result, not a general admission/
startup guarantee. It does not establish physical-device or hardware speed.

Actual route counters prove 158 requests on each selected route and zero on
the alternate route. Rejections, registration failures, revocations and pending
work are zero in every case; both direct ports are positively ready. All four
resource inventories match: 165 entries, comprising 158 native ATP and seven
HTTPS resources. The complete copied production files, source/served scene and
asset hashes also match. Canonical resource-inventory SHA-256:
`069ca736a00f798b109d6de88727b67072a1ae6aef5d345e814fbbb80473318a`.

All cases retain the same recorded quality structure: 55 loaded models,
26 geometries, 21 textures, 96 draws, 83,754 triangles and the actual full-size
4096×2048 sky. Each image ledger records 43 assignments, 42 completions,
one known original PSD failure and 39,342,080 counted image pixels. The explicit
incomplete-texture warning remains required; no substitute or lower-resolution
pixels are introduced. The native observer advances in all four cases, with
zero recorded native position distance. Browser pose distances between paired
screenshots are 0.0061/0.0069 m.

Root inspects all four actual world PNGs. Their visible bridge/material/body
structure matches; authored cloud motion and live avatar articulation differ.
Pixel identity is false. Full RGB differing-pixel fractions are 70.51%/73.02%,
with mean absolute channel differences 9.2621/8.3208 out of255; the independent
sample-grid differences are 9.5276/7.8245. Pair success describes each case's
functional/loading/budget checks, not identical pixels or full native effects.
Observed software cadence is 1.248–1.674 fps, which does not qualify hardware
fluidity or attribute CPU/GPU costs.

The independent supervisor exits naturally with launcher0/cleanup0, zero
remaining owned browser processes and an empty actual browser registry.

- Raw result SHA-256: `65b01df95fc9c013cb0bcc9cb688158a1496aa82b8645a3c2d4d71014844c1b7`.
- Safe filtered route/quality/pixel summary SHA-256: `5001512a2ef91487077aff76a5f7bd4da8f2b583fe7f9af26053636d69f61794`.
- Complete production manifest SHA-256: `b9e763d1dcff0f2ce8d99bda8a05610cbcc236e41e5a5f1d48026c0c476c3d4b`.

The older decoded-image-sharing comparison and passive request-delay diagnosis
remain separate historical evidence. Their failed speedup and correlation
limits are not rewritten by this controlled route result.

## Public fresh native qualification and final repository checks (2026-10-03)

Before the next complete journey, 36 previous actor/run records are copied
into private history with manifest SHA-256
`82d7802756cfc8f1d052c0df4df9073c0fc342678c44bd5696846176aa08ebb5`.
Only the exact owned native client is restarted. The new actor reaches the
actual ordinary Hub spawn automatically, without a lookup retry or exit139,
before separately recorded three-metre placement. Its native view has 53
entities/34 loaded ATP models, actual HTTPS bridge/mannequin, 69 joints and
two meshes. These are native-view counts. Same-launch Qt FST/FBX source hashes
and all six actual service endpoints qualify.

The public `capture-ordinary` → `place-ahead` → `qualify` workflow itself writes
the required observer/source/unused-trial fields. Its result is not edited or
sealed by a private helper. The new actor/session differs, its version-2 trial
is genuinely unused, and the source191/b24 runtime/observerd45 and completed
build records remain unchanged.

- Public visitor qualification SHA-256: `0f85924e1b6109b5fc480f706895ed081d97c1dfe4b9965401d4bf34889aabfc`.
- Separate motion-readiness SHA-256: `b534267e821a88802ddbff2a9783fa80981b1b1e9bec79c59fa2eb687a442ba2`.
- Fixture source-freeze SHA-256: `a10772cd77c3e7fea1f291e44e09e2a18b822b2a30fb162710db5d9e159f9e42`.
- Safe binding proof SHA-256: `84bf1ff9e16b444b89b1703e9e954defe3d63c401bf7c34493c82fcff2b9588d`.

Root independently runs the seven public qualifier regressions successfully;
log SHA-256 `4e1ccf89ceac488433e970d440a47bd86ddfcd9591b2abc3f1c391dafb3bb418`.
After launcher/qualifier/CI changes, the required repository quick profile
passes **34 suites, zero failures, 186.44 s**:

```sh
python3 tests/run-project-tests.py --profile quick --timeout 240
```

Log SHA-256:
`edeb81c2215b7517a33675174b654e241852b4a608441e6f99c26105b6a1b2ab`.
All local CPU checks finish before the independent bounded
`direct-chrome-20261003-g --audio --timeout 180` journey starts on the same
40-file production artifact at 08:13 UTC. At that checkpoint its final result was pending; the completed result follows
below. The earlier f freshness failure remains failed, and no consumed trial is reused.


## Complete current-production Chrome interoperability (2026-10-03)

`direct-chrome-20261003-g` passes **25/25**, with zero page/shader errors,
from 08:13:43.525 to 08:25:02.154 UTC (**11 min 18.629 s**). This is the complete
current direct-route production bundle, not the earlier e snapshot. The actual
frozen 40-file manifest is
`b9e763d1dcff0f2ce8d99bda8a05610cbcc236e41e5a5f1d48026c0c476c3d4b`.
Chrome for Testing 153.0.8010.12 runs the ordinary local tablet/world/input flow.
No build, helper test, additional sampler or unrelated UI/audio test runs during
this journey. The original 180-second scene/1,080-second driver bounds hold.

Direct admission, actual 83-entity historical scene, all 55 real models/available
maps, unchanged ATP/HTTPS bytes, contained sky/source materials, own/native
avatars and all six local tablet applications pass. Actual trusted picking and
jump/landing use the loaded source-model triangles. Native body movement is
sequence 396→400: native X/Z displacement `(-0.00164795, -0.95016479)` m,
actual rendered body displacement `(-0.00164795, -0.94982910)` m, ten real rig
draws and zero evicted body samples. Strict restore advances 425→427 without
primary/restore error. Root inspects both actual upright-body PNGs. The browser
is not teleported by the native-only setup.

Trusted browser keyboard movement reaches a strictly newer actual native peer
observation 496→499. Browser X/Z displacement is `(-0.15051450, -0.66604161)` m;
native receipt is `(-0.15061951, -0.66604614)` m. Exact current host/session/peer
bindings and the original 0.25-metre horizontal tolerance pass. The host proof
loop remains live/fresh; the previous f freshness failure is not overwritten.

Both current-bundle synthetic audio directions pass:

- Native 523.25 Hz → actual Chrome output: 383,387 frames at 48 kHz,
  RMS 0.0266786, matching-frequency amplitude 0.0109295.
- Chrome 659.25 Hz → actual native output: 384,000 frames at 48 kHz,
  RMS 0.0534818, matching-frequency amplitude 0.0092587. Actual browser capture
  advances 120→1,060 frames with zero microphone-frame drops; explicit mute
  and leave stop capture.

These are real native/browser transport and playback observations using private
virtual sources. Physical microphone speech is explicitly false. The separate
real Chrome stock-popup permission result remains component/consent evidence.
Actual snapshot download, closing every peer/worker channel, fresh native
channels on reconnect and unavailable-domain error cleanup all pass.

The independent supervisor observes natural launcher exit 0, cleanup exit 0,
zero remaining owned browser processes and an empty actual browser registry.
Its proof is source-bound to the corrected public launcher; no deadline,
freshness rule or native trial is renewed. The now-consumed native actor is
restored and held for read-only evidence; another motion qualification needs
a new launch.

- Current raw result SHA-256: `d419132dd680f4ab94e2dc4cab26b89dddd7094aa6cd8a87fff55958e40fbf8d`.
- Filtered functional/audio/cleanup summary SHA-256: `03d67527b13ad2fee14326395886b3e792de5b076972d285db364cc4f07386fd`.
- Supplemental final helper/repository checks SHA-256: `3a417c80919131c2e22f6ce7f3ab3392125514539e6fbddd8b3738818d0bd566`.

Physical bidirectional speech, an agreed exclusive hardware-rendering window
and public Hub operator upgrades remain outside this demonstrated acceptance.
At this checkpoint, draft publication and its remote checks were the next step;
their subsequent results are recorded below. No issue is closed.


## Publication byte preservation (2026-10-03)

The repository attributes would normalize three immutable imported SDK files
from CRLF to LF when staging. A first index-byte check correctly fails for
those three files; its evidence is preserved. Narrow attributes for exactly
`ClientTraitsHandler.ts`, `EntityQuery.ts` and `OctreeConstants.ts` disable text
normalization and recognize CR at line endings for whitespace validation.
No upstream source bytes or provenance manifest are changed. After explicit
renormalization, all 416 staged files match their worktree bytes and the
staged whitespace check passes. The provenance checks still qualify the
original immutable renderer and SDK inputs.


## Final read-only native and resource review (2026-10-03)

The final identity-bound review leaves the same native actor stationary, with
its one-use motion trial consumed and the original position restored. Native
source/build qualification, DomainServer and assignment services are unchanged.
The browser registry is empty and the independent supervisor reports launcher
exit 0, cleanup exit 0 and zero remaining owned browser processes.
Invariant/cleanup proof SHA-256:
`3f4d26f25284a908a807726563f88582b35b636987dd0e228a05a95acc796e9a`.

A read-only scan finds 16 AssetServer failed-write log records over the current
build's log lifetime, two printed during journey g and none printed after its
END. Across native services the corresponding printed-record counts are
98/12/0. These are log-record counts, not failed-datagram counts. The two
AssetServer suppression summaries print at 08:13:48 and 08:24:58 UTC. Their
last-reported endpoints bind uniquely to g's initial admitted Agent and its
distinct fresh reconnect Agent. Neither endpoint appears before that run.
This puts the printed summaries at initial admission/early asset flow and
fresh reconnect admission respectively.

The shared callsite flushes suppressed messages on a nominal five-second
interval. It does not identify original send-attempt times, packet types or
individual RTC attempt counts; intermediate repeats can mix UDP/RTC paths and
destinations. No additional functional defect is confirmed, but the specific
send cause remains unclassified. The 25/25 result does not establish that
these warnings were benign or that no native write failed during the run.
Context proof SHA-256:
`56ff63b115368fd0267d9ff2bd90250697d520dcff6fe8dc5cf30f63f9791d5b`.

The separate physical-resource observation at 08:31:39 UTC finds one suspended
physical ALSA source with its two microphone ports and line port unavailable.
Two foreign display processes still hold two DRM descriptors; no exclusive
hardware test window is agreed. Descriptor ownership does not establish GPU
work. The review performs no capture, routing, resource takeover or restart.
Physical speech and hardware rendering remain unqualified. Resource proof
SHA-256: `fded108c38a15e9878e4bbfec8cf3cf95b166cf39dbade9e826a064bf2f7ef5e`.


## Draft publication and completed code CI (2026-10-03)

The published code head contains three reviewed implementation commits: native transport
`9e95caeebb8adbf66377ffb83c65a96d2827f58f`, browser client
`9fb4169ab17982de841caea6dcceb953179a7676`, and CI qualification
`00c68dc31d6137ee8cc6d2d81dc25cf41dac68f8`. The effective push URL targets
`noah-be/overte`, with no URL rewrites; the installed guards match the reviewed
version. [PR #1034](https://github.com/noah-be/overte/pull/1034) was created and
read back as a draft against fork `main`. Material AI assistance is disclosed.

At 10:14:03 UTC, all 17 reported checks pass and two dependency-inventory checks
are skipped by the existing selection policy; no check remains pending or fails.
This includes browser, native, full host, documentation, workflow security,
CodeQL, branch policy, reuse and dependency policy checks. Snapshot proof
SHA-256: `dbe9c599fbccce753486144e87893a58d3f281aa87df63eac6646fa2a8e935b9`.

Both dedicated native runs build and pass all six expected CTest programs with
zero failures/skips. Push run
[37111728009](https://github.com/noah-be/overte/actions/runs/37111728009)
has 1.523699 s of tests in a 35 min 05 s job; PR run
[37111784222](https://github.com/noah-be/overte/actions/runs/37111784222)
has 1.405432 s of tests in a 27 min 19 s job. These test times do not describe
the compilation jobs. Downloaded JUnit SHA-256 values are
`28daf2c1e4518b7ef273fc6bf127bd3b9d6c22e903e674698a71f250b8b818ab`
and `06e2c7d33f328cf0b4dffdfe4583851ef9d41314830f945e64d8f3f02767be8b`.
The general native job in
[repository run 37111784430](https://github.com/noah-be/overte/actions/runs/37111784430)
also completes successfully at 10:08:42 UTC. Remote CI does not establish
physical microphone speech, hardware navigation or public Hub support.

Its downloaded diagnostics independently confirm **33/33** selected CTest
programs, no failures/errors/skips/disabled cases, and matching Qt XML coverage
with 282 pass incidents across 218 functions. Build time is 3,625.486 s;
actual test execution is 5.112 s; whole-job time is 3,876 s. CI checks out PR
merge candidate `0f96e7eb708227c976030abcee4760ba69597b1b`, whose parent is
the published code head. Both commits have the identical code tree
`d0925d0ac3e77d2f2927155958dfbdd8ca3bc6a2`; their commit objects are distinct.
The downloaded JUnit SHA-256 is
`7b190e52180a6a2198ccfbfbda5292704d7155b93c6737695bfb516ab5607d83`;
filtered diagnostic proof SHA-256 is
`4c429d7b513aa8ab14438c17bcd392783fc6f5b57c3cd823c24b5bf04c4c0349`.

The retained journey-g tablet PNG was independently inspected: the upright own
Woody avatar appears in the foreground and the distinct upright native avatar
appears farther along the actual bridge. The original texture warning remains
visible. Actual geometry evidence records 55 loaded models and two loaded
avatars, with own third-person/body/rig/model visibility all true. Screenshot
SHA-256: `9fcb9996ece059171895467cedb0bf883dfb53819e287a3234d67a9e2c3bd82b`.
This is inspection of existing software-rendered evidence, not a new run.

A separate 09:26:48 UTC read-only resource refresh finds the same suspended
physical ALSA source, two unavailable microphone ports and one unavailable
line port. Four verified foreign registrations cover nine inspected processes;
two display owners hold two DRM descriptors. This establishes resource ownership,
not GPU activity or an agreed exclusive window. No capture or hardware context
is opened. Proof SHA-256:
`01982b12be96862fa47d6d9eff12d1cbd59ee1eceb07e0b5eb1a9afc5117c6a9`.

[MANUAL_ACCEPTANCE.md](MANUAL_ACCEPTANCE.md) documents the proposed final check
using a fresh owned profile, physical devices, the complete qualified browser
bundle, process-local fixture trust, actual renderer/frame diagnostics, human
phrase repetition in both directions and bounded identity-based cleanup. Its
hardware steps remain **PROPOSED / UNQUALIFIED**. Available-resource inspection
and snippet syntax checks do not count as human speech or hardware acceptance.

The documentation follow-up passes the required repository quick profile again:
**34 suites, zero failures**, 199.08 s. Log SHA-256:
`fa686b46d07079d228fec23b833e4fe34e846ef930c2d73e63ee8659b90a3981`.
All 198 workspace Markdown documents and incoming local links pass; the existing
documentation-checker regressions pass 24/24 and repository policy displays match.
The proposed guide passes syntax checks for two Bash fences, one embedded Python
program and two JavaScript snippets. No hardware clients or capture are launched.
