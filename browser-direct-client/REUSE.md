<!-- Copyright 2026 Overte contributors; SPDX-License-Identifier: Apache-2.0 -->

# Browser renderer reuse

This implementation is materially AI-assisted. Review and acceptance evidence
belong in `docs/browser-direct-client/`; successful unit tests do not establish
direct server, browser, microphone or native-client interoperability.

The browser renderer is reused from `noah-be/overte` commit
`261fc77c1c322410f6096e65dcff0388c372286d`, the committed snapshot of the other
browser-client topic branch when inspected. Source files were read using
`git show <revision>:<path>`. No uncommitted source files, processes or test
resources of that session were used. `reuse-manifest.json` records the exact
source paths, Git blob IDs, destination paths and original byte lengths.

The manifest retains all 95 original Git blob IDs and byte counts. Default
`npm run verify:reuse` checks 87 exact inputs and eight adapted current SHA-256
digests plus their modification notices without a historical checkout.
`node tools/verify-reuse.mjs --source /path/to/original/overte` additionally audits
all 95 original Git objects. Six provenance regressions cover equal-length
tampering, missing or malformed adapted hashes, absent modification notices and
original-object integrity. `node --test e2e/reuse-provenance.test.mjs` passed all
six cases with zero failures and zero skips.

Reused rendering code depends on Three.js 0.186.1, three-mesh-bvh 0.9.15 and
Draco 1.3.4. Its FBX/glTF/OBJ/FST loading, native material properties, texture
image/source caches, worker preparation, capsule collision and avatar rigs
execute on the visitor's device. `BrowserWorld` receives decoded native entity
and avatar properties from the dedicated native session worker and resolves assets through the
current direct session. HTTPS resources retain their own origin and CORS rules;
ATP resources are fetched by the browser using the native AssetServer transport
and a browser-local Service Worker. No gateway, native mediator, server renderer
or video tablet was copied.

The only initially modified reusable files are:

| Destination | Change |
| --- | --- |
| `src/world.ts` | Expose local tablet camera control and a test-only image-cache baseline; resolve native asset dependencies; render an actual contained Zone equirectangular skybox; expose explicit bounded per-entity main-camera draw observation and read-only raw native joint/default plus real loaded bone/owner transform evidence; retain real model geometry when a declared texture fails, with bounded explicit incomplete-texture evidence and a persistent local warning. |
| `src/audio.ts` | Browser permission/device lifecycle retained; transfer one duplex AudioWorklet/session-worker port without requesting microphone access; retain explicit capture consent, real-track stop, stale-permission guards and bounded numeric UI statistics. |
| `src/audio-worklet.js` | Replace the gateway's 48 kHz/20 ms framing with native 24 kHz/10 ms framing, bounded 100 ms jitter queue and linear output resampling; transfer exact mono/stereo PCM directly to the session worker with at most ten unacknowledged frames; reject stale audio/unmute/ACK epochs after leave or mixer mute. |
| `tools/build-notices.mjs` | Remove unused GIF dependency; preserve Overte/SDK dependency notices and the full bundled TinyEXR/OpenEXR additional source licenses. |
| `tests/prepared-fbx-cache.test.ts` | Replace the obsolete gateway URL adapter case with the real browser's direct HTTPS Unicode URL encoding; retain the cache bounds and hit assertions. |
| `tools/prepare-default-avatar.mjs` | Preserve immutable original Woody license, contributor attribution and Overte FBX import links in the packaged manifest and license; keep all six native asset bytes unchanged. |
| `src/world-data.ts` | Preserve raw native nullable joint pose fields, hierarchy and source defaults rather than inventing identity/zero poses. |
| `src/avatar-rig.ts` | Convert absolute rig rotations to parent-relative model rotations using the loaded hierarchy and declared geometry rotation; restore original authored defaults on native default flags; keep model-unit translations and loaded bone scales. |

The separately copied `WorldPresentation` and native tone curve are an unused
renderer prototype and its companion tests; importing them does not change
`BrowserWorld`. They retain their original MIT-derived tone-curve notices.

Current-main integration also carries forward the bounded keyboard-transition
repair accepted in PR #1023 at `ee477a960d7e82920e785930647d2f6f105750d7`.
The direct client's actual input handlers and animation consume the same 60 Hz
simulation clock with the existing 250 ms stall limit. Input transitions advance
the previous key state before changing it, retaining a press that occurs entirely
between rendered frames. Nine actual-World CPU regressions cover movement,
idle-time attribution, direction changes, collision, focus/visibility revocation,
input disable/disposal, pending support, shared-clock accounting and invalid
timestamps. The original renderer manifest remains intact; the adapted world
file's current SHA-256 and modification notice include this accepted repair.
Renderer experiments such as compressed-color admission, asynchronous upload,
shader warmup and matrix memoization remain disabled initially. The existing
image/source and prepared-FBX caches run with their original bounds. An explicit
`?benchmarkImageCache=off` acceptance URL bypasses decoded-image sharing through
the stock Three.js texture loader. It keeps texture bytes, samplers, color space,
geometry, renderer settings and all other caches unchanged. Compare network
transfer/decode counts, world loading phases and pixel output on the same actual
scene in separate fresh browser profiles; report warm HTTP caches separately.
`getPerformance().imageLoading.enabled` records the chosen benchmark arm.
Performance claims require measured direct-session comparisons at unchanged
display quality. Worklet and cache unit durations measure only those isolated
host operations; they are not join-time or rendering-performance evidence.

The minimum Zone skybox adapter uses actual source images, including original
EXR files decoded by the pinned [Three.js EXRLoader](https://threejs.org/docs/pages/EXRLoader.html).
It preserves the full source resolution and HDR texture values. Native visible
Zone selection follows smallest volume then canonical UUID, with independent
enabled/disabled/inherit modes and oriented box, sphere/ellipsoid or cylinder
containment. Rotation, registration point and authored skybox color are retained.
The source semantics were reviewed against `EntityTreeRenderer.h/.cpp`,
`EntityItem.cpp.in`, `graphics/Skybox.cpp` and `graphics/Light.slh` in this checkout.
Compound convex hulls, cubemap cross/strip layouts, procedural skybox shaders,
and native ambient/key-light/haze/bloom/postprocessing parity remain unsupported
and are recorded explicitly. A failed skybox remains a failure even if the
authored solid color is visible while loading. EXR headers and transfer sizes
are bounded before pixel allocation; an unsupported size fails without resampling.

`overteObserveEntityRendering` observes at most eight already-loaded entity owners
for at most five seconds, then restores their original callbacks. It records
actual main-camera `onAfterRender` submissions and assigned texture sources,
without changing the scene, camera, material, geometry or graphics quality.
Draw submission alone does not prove visibility of every fragment; real scene
PNG evidence and unchanged source/served asset hashes accompany acceptance.

The real bundled mannequin is copied from this worktree's versioned
`interface/resources/meshes/` during `predev`/`prebuild`. The preparation script
verifies all six original SHA-256 digests before copying any output and bundles
their repository Apache license. A generated asset is never substituted for
world or participant data.

The original character is Woody, published by High Fidelity with Haptic Monkey
as an original contributor. Its immutable [license metadata](https://raw.githubusercontent.com/overte-org/overte-content/ed9ac884c274990210f6c62fed7f5e8837d170aa/Bazaar/Avatars/woody/resource.json)
and [package metadata](https://raw.githubusercontent.com/overte-org/overte-content/095127bbdee8311e3f06349cf3d450dd3e1c3a28/Bazaar/Avatars/woody/package.json.backup)
record Apache-2.0 and that attribution. The [Overte import](https://github.com/overte-org/overte/commit/e8d79cfb9baa38cd7a8f4f63d509330b9c306f1b)
removed broken eye-blink blendshape normals from the imported FBX, replacing the
previous baked FBX. Bundled bytes
remain the six verified repository/native resources; byte identity to the
separately hosted original Woody FBX is not claimed. The generated manifest and
license preserve these links and attribution.

The adapted joint consumer follows native `Rig::copyJointsFromJointData` and
`AnimSkeleton::convertAbsoluteRotationsToRelative`: explicit absolute rig
rotations enter the declared model frame and become relative to the loaded
hierarchy; default flags restore original model poses. Relative translations
remain in authoring units and loaded bone scales are preserved. Three focused
regressions failed against the original consumer and passed after this repair;
the original test file remains byte-exact and the added cases live in
`tests/native-avatar-rig.test.ts`. The retained `direct-chrome-20261003-d`
result observed an upright actual native body but failed newer-position delivery.
The fresh final-source `direct-chrome-20261003-e` run subsequently passed all
25 criteria, including actual native-to-rendered-body motion and strict restore.
These observations do not establish all native animation/rig behavior.

Separate test-only, renderer-free probes retain the earlier production worker
unchanged. The 15-second stationary probe observed 43 raw native joint-section,
actual worker-post and actual facade joint changes. A fresh guarded native
one-metre −Z move then reached all three pose boundaries with zero horizontal
displacement error, and strict restore returned to the original position. These
results diagnose the direct native pose pipeline; they did not retroactively
change the earlier failed full rendered-body criterion. Bounded passive wire/event diagnostics omit
received identities, HMACs and payloads. The full driver additionally labels its
page Worker-message observation distinctly from a private facade callback.

Actual slow-acknowledgement outbox regressions subsequently reproduced starvation
of avatar/permission delivery behind continuous entity upserts. The reviewed
source repair retains an existing snapshot's queue position only across the
same generation's independent trailing upsert/avatar/permission updates;
removal and lifecycle barriers remain ordered. Queue limits and scene/texture
quality are unchanged. A fresh final production build passed the complete
25-criterion Chrome journey against the final immutable native runtime. Native
sequence 446→449 moved about 0.950 metres in Z; the actual loaded body followed
about 0.950 metres and submitted ten main-camera body draws. Strict restore
475→477 returned to the exact original horizontal position. Both separately
labeled synthetic microphone/mixer directions and natural cleanup also passed;
physical microphone access remains a separate qualification. A subsequent
isolated Chrome permission run used actual inspected browser-UI Deny/Allow
buttons in two fresh profiles, with no permission API overrides, then verified
real BrowserAudio capture and track/context cleanup against only the private
virtual microphone. It establishes that permission/component flow without
claiming physical speech or additional native-voice acceptance.

Four fresh real-scene profiles then ran ON/OFF/OFF/ON at the same source bytes,
settings and bounded deadlines. All four loaded 55 geometries and the available
maps, with the same explicit unavailable PSD. Sharing reduced observed Image
assignments from 105 to 43 (59.05%) and reported completed-image pixels from
60,989,440 to 39,342,080 (35.49%). These are repeated image-loading measures,
not isolated decoder CPU, physical RAM or GPU-upload savings. Mean full-scene
time was 174.768 seconds ON and 171.570 seconds OFF: no full-scene speedup was
observed. All four resource-path/body-size structures and source/served hashes
matched. Static loader inspection preserves original source dimensions and
independent caller samplers/color spaces; no runtime per-material sampler
inventory was captured. Actual PNG differences include live native articulation,
sky/cloud motion and authored rotations. The software renderer ran about
1.32–1.35 frames per second; hardware fluidity is not established.

A subsequent test-only three-realm dispatch observation used that exact
production bundle and unchanged real scene. All 55 geometries were ready in
191.513 seconds. Its 158 requests showed main-thread forwarding arrival waits
of median 1450.20 ms/p95 2373.10 ms; native mapping/get/hash await was
22.00/1045.60 ms. Replies already travelled directly from the session worker
to the asset ServiceWorker. The observation is partial: the late reply listener
could not qualify response-construction duration (79 negative intervals and
79 quantized zero intervals), with no missing stages or observer losses.
Concurrent timing sums do not establish a critical-path saving, and disabled
CPU/GPU timers do not support GPU-only attribution. No production transport
optimization or additional speedup is claimed by this diagnostic.

An actual source texture failure leaves the corresponding original geometry
visible with its declared material values and all successful texture maps.
This follows native `NetworkMaterial::isMissingTexture()` failure handling;
session revocation and abort remain fatal. Bounded per-model evidence and a
persistent local warning identify incomplete textures. The historical dock
material declares an unavailable `bridges_d.psd`; no similarly named baked PNG
is substituted, and full original texture parity is not established.

The local tablet consists of DOM applications for domain connections,
participants, avatar identity, microphone/output control, renderer graphics
and visitor-rendered PNG snapshots. Its initial entity interaction is selection
and inspection of actual world entities. Avatar identity and microphone samples
use the native transport. Native QML tablet applications, arbitrary entity
scripts and editing without native permissions are not provided by this UI.

## Imported source bytes

The three SDK sources with upstream CRLF line endings have narrow `-text`
attributes in `.gitattributes`. This preserves their immutable source hashes
in Git as well as in the worktree. `whitespace=cr-at-eol` recognizes those
line endings without relaxing whitespace checks for other files.

## Local commands

From `browser-direct-client/`:

```sh
npm ci --ignore-scripts
npm run verify:reuse
npm test
npm run build
npm run dev
```

The development server uses loopback port 5187 and the production preview uses
4187, independently from the other session. Vite has no gateway proxy. Serve the
production `dist/` directory at a secure origin with its third-party notices and
bundled mannequin files. The domain/server transport configuration and deployment
requirements are documented under `docs/browser-direct-client/`.

The synthetic worklet tests use real local MessageChannels to prove native PCM
framing, channel order, mute revocation, stale audio/unmute epoch rejection,
replacement-port isolation, stalled-peer ticket credit and bounded queues. The mocked microphone lifecycle tests prove that
permission results after leave stop their tracks. Neither exercises a physical
microphone. No browser, desktop or GPU process was started by the reuse step.

The vendored SDK was also repaired for modern typed-array/browser APIs without
relaxing TypeScript checks: owned private-key/plaintext buffers, bounded packet
views and deep packet clones, native `FormData` string/Blob overloads, correct
binary property return types and exact RTC/UDT datagram slices. The offset/clone,
binary message, real RSA signing and native multipart regressions run locally
without accounts or remote requests. Native mixer `NoisyMute` events immediately
stop the browser capture track through the `microphoneMuted` session event.
