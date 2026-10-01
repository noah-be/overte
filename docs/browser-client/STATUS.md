# Browser client status

Last updated: 2026-10-01. **Original baseline passed; additional mandatory Tablet and online-Hub implementation in progress.**

## Current implementation and next step

Published branch: `feature/main/browser-client`, commit
`cee2402852b77be38d35882e41c89bde80c64a90`, draft PR1023. The goal remains active;
no endurance run is required or scheduled.

The newest loading change coalesces session-owned FST/material/texture-metadata
source text with exact permission-generation checks and bounded byte storage.
**627/627 component tests**, **114/114 browser cases**, all **34/34** required
repository checks, Actionlint and Zizmor pass. The production build also passes.
A fresh stockFirefox
Hub run reduced two-session FST/texmeta/materialJSON request counts from
492/524/686 in the preceding Image cohort to190/266/182. Its final World
retained319small texts in0.39MiB with532hits and zeroevictions. Source keys
never cross visitors or approval generations. Firefox functional movement and
rejoin passed within0.74mm of native, but all four fluid gates still failed
(last walking25.9FPS). Chromium's matched fresh cohort passed allfourfluid gates at43.1FPS and
34ms p95; both native position errors are below0.61mm.
These are individual live snapshots, not an isolated causal latency guarantee.
[Runtime design and exact limits](WORLD_SOURCE_TEXT_LOADING.md),
[all five actual cohorts](evidence/hub-source-text-runtime-20261001.json).

The subsequent working tree integrates bounded opt-in CPU/GPU timer diagnostics,
the browser-owned native Tablet Graphics adapter, and default-off native culling
and static winding experiments. **584/584 component tests** and **19/19 actual
backend kernel tests** passed before the Image-role correction. All12 Image
contracts and both stock-GPU fixtures subsequently passed: opaque/alpha-mask
sRGB colors, orientation, shared sampler uploads and cancellation remain correct.
[The actual Image proof](evidence/image-compressed-world-20261001.json) establishes
safe compressed-color admission for real BrowserWorld Image entities, not a
whole-Hub latency gain. Both fresh production Hub cohorts are recorded above.

Both actual native Qt Graphics pointer journeys passed twelve changes plus
leave/rejoin in Chromium153 and stock Firefox156. Actual framebuffer dimensions
change1280x900→640x450 at50%, and2560x1800 at200%. Separate BrowserWorld GPU
fixtures in both bundled engines prove projection, local-light pixel effects and
camera collision constraints. [The preserved evidence](evidence/tablet-graphics-runtime-20261001.json)
includes earlier failures; full graphics/native Tablet parity remains open.

The actual culling World GPU fixture passed both browser engines after its first
relative-asset-address failure was corrected. It checks six authored positive/
mirrored face and normal cases, unchanged draws and stable programs. CPU cases
passed21/21. The experiment stays off pending independent native pixels and
strict Hub measurement; no loading or FPS benefit is claimed.

[Short actual timer cohorts](evidence/hub-gpu-timing-runtime-20261001.json) preserve
unchanged density and all four fluid/reconnect gates. Chromium passed; Firefox
still failed fluidity and correctly reports unavailable GPU timing. Chromium's
matched elapsed/CPU samples are diagnostics, not a fragment-only cost or causal
speedup. A separate three-second process observation found the owned idle local
native observer using7.016 CPU cores; an unrelated native process used2.740 and
was preserved. The private CUSTOM refresh experiment remains **OFF** after three genuine
Tablet failure cohorts. Fresh standalone native readback confirmed its settings
and connected state, but this does not establish sandboxed-worker Tablet/audio
acceptance or isolated CPU savings. The normal default passed both Graphics
journeys. No existing observer or unrelated process was restarted.

The actual cee240 GitHub repository-check run36846664719 passed every required
job, including native build, documentation, workflow security and project tests.
Browser CI36846526712 failed before tests because the signed Noble package keeps
its namespace profiles in `/usr/share/apparmor/extra-profiles`, rather than the
assumed `/etc/apparmor.d` location. Its early cleanup also failed on a missing
process registry. The reviewed corrections pass19 package/profile contracts and
11 actual cleanup contracts; signed-package hashes are retained in
[the package audit](evidence/ubuntu-apparmor-package-audit-20261001.json).
Strong capability-denial profiles remain intact. The existing local Fedora
Jenkins agent is a candidate for complete repeatable isolated native/browser CI;
the root-owned namespace smoke actually passed private ports, tmp/X isolation
and nested normal unshare/bwrap. The corrected preparation installer namespace
also passed with all five capability sets zero. Complete Jenkins execution is
still unproven; the exact-source isolated runner is implemented and under review.

An additional independent native Image comparison connected successfully and
verified deletion of all four owned fixtures while preserving the seven baseline
entities. Its pixel test failed because a universal variance threshold rejected
the valid dark original texture: the source itself has lower variance than the
threshold. Native/source correlation was0.959 with1.50RGB mean absolute error.
The content-derived oracle is being corrected; no native Image parity pass is
claimed from this failed run, and its source-frozen failure remains preserved.

Further actual cohorts corrected Canvas sampling and explicit emissive Image
presentation: the browser now matches its audited source at0.88RGB error and
0.986detail correlation. The live native64-grid Canvas oracle still fails0.9;
independent native Image parity remains open. Bounded CPU/Pillow analysis of the
same screenshot passes0.959correlation, exposing a remaining Canvas reduction
sampling issue. A deterministic area reducer is being prepared. The author counts three
frames strictly after FINISHED and invalidates stale render-branch signals.
[All five actual negative cohorts](evidence/native-image-runtime-20261001.json)
remain retained; no pixel threshold was lowered. The added preset selector has
eleven CPU/native-source contracts and six exact read-only kernel mounts;
its real native Qt click journey is running.

The final repository rerun exposed a pre-existing cancellation-fixture race:
`exists()` could observe an empty identity marker during `write_text()`. The
fixture now publishes its complete PID JSON with an atomic same-directory rename;
all original cancellation/deadline/process-reaping assertions are retained.
The thirteen real self-tests and all thirty-four quick suites passed afterward
(200.67seconds). The original failure log remains private and is not called a pass.

Next: finish the content-derived native Image proof and publish the reviewed
loading/Graphics/CI checkpoint, run complete isolated CI, and complete
safe Create/edit/delete through the actual Tablet, then measure the resource
and rendering changes in stock Firefox/Chromium `overte_hub`. Continue faster
world/texture admission work alongside those checks. Full native feature parity,
all supported graphics controls/profiles/scan and Firefox fluidity remain open.

## Published embedded-loading checkpoint

The published cee240 continuation integrates bounded embedded FBX images into
actual BrowserWorld. **509/509 component tests** passed with the default-off reviewed World
zero-light integration and the actual Create route correction; **108/108 browser cases** passed with the embedded
runtime and standalone zero-light fixture. Both stock GPU browsers passed exact
embedded image decoding, twenty rendered frames, one shared-source upload,
independent samplers, real model cancellation and World cleanup. Earlier fixture
failures remain in [the curated proof](evidence/embedded-world-gpu-20261001.json).

The short strict Hub cohort records **44 unique embedded images and32 cache
hits**, compared with74/2 in the prior runtime. Chromium passed all four unchanged
fluid/rejoin gates at47.1FPS and23.554seconds to model-task readiness. Firefox
rejoined and synchronized within0.54mm, but failed all four fluid gates at27.1FPS;
its task-readiness observation was21.013seconds. These are different live
snapshots, not a causal wall-time speed guarantee. An earlier Firefox diagnostic
fell23.52m and failed the nativeY observation; that negative run is preserved.
See [all four runs](evidence/hub-embedded-runtime-20261001.json).

The b067 hosted browser CI actually failed: Ubuntu AppArmor denied user-namespace
mapping, and the native input compile lacked GL headers. Repository workflow
security also found two ShellCheck SC2016 blocks. The current changes add signed
GL/package dependencies, normal shell wrappers, and preparation of unchanged
packaged bwrap/unshare AppArmor profiles only when their main profile is absent.
Twelve helper contracts and eight safe evidence-curator contracts pass; no profile or sandbox requirement is weakened.
Actual hosted rerun remains required. Local actionlint and Zizmor pass, but local
ShellCheck is unavailable. Ubuntu ELF/plugin closure passes; the isolated GUI
probe failed X display connection. Correcting the diagnosed CLI display-override mistake produced actual native
protocol,GUI-script and authenticated frame-capture passes. Normal container
namespaces remain denied; these results do not establish Ubuntu hosted
isolation or a shared-world journey. Owned audio-child completion/timeout cleanup now passes six
real process tests; both fresh stock Chromium154 and Firefox156 native joint flows passed all18
checkpoints, including both synthetic voice directions, interaction, collision
and reconnection. [Fresh evidence](evidence/core-embedded-runtime-20261001.json).

The exact-zero-light actual Hub experiment passed Chromium fluidity but still
failed Firefox fluidity and showed no measured improvement. The browser entry
point opt-in was removed; the reviewed option remains disabled by default.
Actual Create,Settings and More GUI discovery passed; no functional editing,
browser graphics effect or More installation claim follows from menu capture.
All34 prescribed repository checks passed in199.70seconds.

Next: profile actual GPU/CPU rendering, complete native Create and
browser-effective Graphics Tablet flows, verify the matching Firefox core,
publish the reviewed
continuation, and inspect the real hosted results. Full Tablet/native feature
parity and Firefox fluidity remain mandatory and incomplete.

The published functional baseline is on `feature/main/browser-client` at
`cee2402852b77be38d35882e41c89bde80c64a90`, in draft PR 1023. The expanded user
scope remains active; publication is not completion of the added requirements.

The current loading runtime passed **468 component tests**, a production build
and **106 browser cases**. Initial support also passed 24focused CPU and 4 browser
floor/geometry cases. Its safeguard uses actual triangle contact, expires without
repeated BVH scans, does not re-freeze jumps, and resets on return to spawn. Fixed
60 Hz movement passed equal-speed, collision, jump and spawn-reset checks at
60/30/10/4 rendered FPS. Both current stock Chromium 154 and Firefox 156 passed all
18 short actual local-domain/native checkpoints, including synthetic voice in
both directions, object interaction, collision, clean leave, rejoin and mouse
look. Startup distribution hashes still matched when evidence was curated; the
harness does not continuously attest the filesystem. See
[current native/browser evidence](evidence/core-compressed-runtime-20261001.json).

Actual detached model triangles permit movement before textures finish. The
prepared-FBX cache, model scheduler and approved compressed-color material path
are now integrated. The latest read-only always-muted Hub cohort reached model
task readiness in **23.784 s in Chromium  / 23.469 s in Firefox**, compared with
30.072 s / 28.941 s in the preceding progressive-geometry observations. These are
individual different live snapshots; readiness includes failed model tasks and
is not full texture success or an isolated causal speed guarantee. Each loaded
293 models, and asset/format errors remain. Source, distribution and three owned
runtime helper hashes match for both sessions. Chromium passed four fluid gates
at about 44.7 FPS; Firefox failed four at about 27.1 FPS. Their measured drawing
buffers are 1280×800 and2133×1333 respectively; no resolution or acceptance
threshold was lowered. Native initial/rejoin pose differences are below 0.8 mm.
See [loading evidence](LOADING_EVIDENCE.md) and
[the actual compressed runtime cohort](evidence/hub-loading-compressed-runtime-20261001.json).

The actual color cache retained 97/95 compressed textures within 64 MiB, with genuine
GPU uploads. The two separately audited KTX examples are larger than PNG over
the network; universal bandwidth savings are not claimed. Privacy-safe source
counters reveal 74 unique embedded Blob image URLs with only 2 cache hits in each
first session. Bounded embedded reuse is now integrated and separately measured above; this paragraph describes the preceding compressed-runtime cohort.
Linear native presentation and glTF RGB helpers passed 14 CPU and 4 actual GPU cases,
but remain unintegrated, alongside native culling/winding and GPU-timer proposals.
Their standalone evidence does not establish runtime parity or performance.

Portable system host tools passed 12 path/CLI/negative-preflight contracts. Actual
Ubuntu 24.04.5 dependency closure passed six pinned native/Qt/input ELF targets;
Fedora preflight passed ten ELF checks, kernel/bubblewrap namespaces and private
Pulse modules. Ubuntu GUI, isolation and joint native journey remain pending.
The actual-native CI job now requires normal fail-closed preflight and unchanged
short Chromium/Firefox core assertions, uploads only curated aggregate evidence,
and has six passing curator contracts. Its first hosted runner failed as documented above; the corrective runner result is pending.
All **34 repository checks** passed again with the actual-native CI job
(`browser-client-native-ci-project-tests.xml`, 164.00 seconds).

An earlier source-bound public `overte_hub` journey passed in stock Chromium 154
and Firefox 156. Both engines passed unchanged loaded-world, walking and
rejoin gates: at least 30 FPS, p95 at most 66.7 ms and steady stalls at most
250 ms. Representative final loaded measurements were 46.0 FPS in Chromium
and 31.3 FPS in Firefox; replicated native poses differed by less than one
millimetre. Source-specific versions and all four gates per engine are in
[public-hub-fluid.json](evidence/public-hub-fluid.json). Those measured GPU
sessions do not guarantee every device or public domain. Missing asset warnings
and earlier failed runs remain recorded. The new alpha renderer is not covered
by these historical whole-world measurements.

Genuine Places passed seven fresh-worker handoffs, Bookmark/Home restoration,
Back/Forward and actual Hub directory entry. Genuine Chat passed two-participant
Unicode exchange in both stock engines. Snap/files/People passed again in both
stock engines, now with an actual **5,000 ms GIF**, PNG, visitor upload/download,
Qt Unicode rename and selected-text clipboard. These app flows do not establish
complete Tablet parity. A genuine two-fresh-native-worker persona journey also
restored Unicode names, default avatar/scale and four version-three favorites;
see [visitor-persona-native.json](evidence/visitor-persona-native.json).

The actual default FBX rig matches all 67 browser bones to the independent native
pose within one millimetre (maximum 0.142 mm). Genuine Kim selection and Emote
joint synchronization passed numerical checks, and the corrected Kim screenshot was independently inspected on 2026-10-01:
the full-size textured avatar is visible. Its diagnostic unposed geometry bounds
do not describe the actual skinned rendered pose. The cause was authored FBX opacity zero,
which native Overte interprets as opaque. The source fallback and real binary
FBX regression pass. Native texture alpha classification was independently
verified on the actual Hub PNG/KTX; leaf-card pixels previously black become
exactly 86,224 background pixels. Root renderer integration now honors native
alpha eligibility, explicit opacity modes/cutoff and uniform opacity, without
using RGB black as a transparency mask. Whole-Hub verification is pending.

## Restored access and current verification (2026-10-01)

The user enabled CLI Full access. Actual probes now confirm topic-worktree
writes, local TCP listeners and `/dev/dri`. The isolated domain, assignments,
independent native participant, private audio services and gateway are running;
stored process identities were checked before restarting only the owned gateway.
The canonical checkout and unrelated work remain untouched.

The previously restricted continuation was applied to this topic only after all
35 original file hashes and `git apply --check --whitespace=error` passed. All
35 resulting hashes also passed. The standard production build now passes in
the full checkout, and the ordinary `npm test` passed **314/314** with no skips. The new authority-bound
asset cache then passed **331/331** component tests, including real HTTP and
revocation/cancellation tests. All **34/34** repository checks passed. Browser
checks initially passed 83/88; the five failures were corrected test oracles
(quaternion rounding, analytic alpha blend and one-texel cube-edge filtering).
All 16 affected cases subsequently passed; the full final suite must be rerun.
Historical public-Hub measurements do not prove the new alpha renderer bundle.

Real offline Firefox 155 tests additionally passed alpha/image-worker caching,
exact five-percent classification, shared cancellation, bounded queue overflow
and recovery; seven real sky-decoder/worker/bitmap/fetch-lifecycle cases passed.
Those restricted runs had no WebGL2 and are component evidence only. New genuine
GPU, Kim appearance and shared native/browser journeys remain required.

The source restores native FBX alpha eligibility, shipped last-wins diffuse
bindings and scalar translucency; fixes model-texture deadline/abort races; and
releases failed FST/material resources without disposing retained shared maps.
The shipping native CPU FBX audit passed eight inputs and six negative controls.
[Zone effects](ZONE_IMPLEMENTATION.md) remain unintegrated pending their reviewed
native ambient adapter and genuine GPU/native comparison.

Actual current-renderer short shared native/browser flows passed in stock
Chromium 154 on the NVIDIA desktop GPU and stock Firefox 156 headless. They
include both synthetic voice directions, collision, interaction, clean leave,
rejoin and movement. An earlier Firefox headed automation failed before joining at its
BiDi viewport-resize command; that failure is retained. Exact public window sizing
now succeeds without viewport emulation or changing the native pixel density,
and two later actual headed Hub journeys completed their functional flow. These journeys ran
before the latest asset-cache gateway restart, so refreshed joint acceptance of
that runtime and the loading cohort remains pending. The fresh Kim Tablet
selection passed on the updated gateway and its screenshot shows the avatar.

The new actual muted/read-only Hub baseline loaded 297 models and 75 mesh
colliders; loaded-world and walking fluid gates passed in stock Chromium. World
loading after admission took **42.125 seconds** and issued **1,303 asset HTTP
requests for 664 unique URLs (639 duplicates)**. The user made texture/world
loading an immediate priority; authority-bound byte deduplication and per-world
image sharing/parallel decoding are now being implemented and compared against
this baseline. The authority-bound gateway cache avoided **638 repeated upstream
downloads**, with **38.559 seconds** to all model tasks finished versus 42.125
seconds before (8.46% in one pair, not a statistical performance guarantee).
See the frozen [before](evidence/hub-loading-before-session-cache.json) and
[after](evidence/hub-loading-after-session-cache.json) evidence. Full frontend
texture reuse and worker preparation are being tested separately.

The new per-world image cache shares decoded sources while retaining independent
material samplers and authorization URLs; independent material maps load in
parallel. Two owned workers now normalize/decode FBX off the render thread.
Actual production-built worker proofs passed in bundled Chromium 153 and Firefox
155 for five native/model fixtures: exact prepared bytes, geometry, material
groups and skin bones match the prior pipeline. Real stalled-worker termination
and transferred-buffer cleanup also passed. These CPU proofs do not establish
whole-Hub loading speed. The image GPU fixtures exposed incorrect session URLs and an incorrect
assumption about ACES grading in their original fixture. Exact analytic pixel
oracles now pass in both engines, preserving actual application tone mapping.
All **94/94 browser cases** passed; two additional genuine alpha-worker
cancellation/reuse cases also passed. Default CI worker proofs now pass three
fixtures in both engines, including truly encoded ordinary/native-ID Draco.
No mock decoder or public-world asset redistribution is used in that CI proof.

The current same-build Hub profile passes all four movement/rejoin gates in
Chromium, but **Firefox fails all four fluid gates at roughly 26 FPS**. Both
render at their measured viewport density; Firefox's native DPR is 1.667 versus
Chromium's emulated 1.0 (application cap is 2), so this is not an equal-pixel
performance comparison. See [loading evidence](LOADING_EVIDENCE.md). Full texture
success is not inferred from an empty model queue; existing asset errors remain.

Actual stock Chromium 154 and Firefox 156 worker benchmarks measured about
1.1–1.2 seconds spent merely yielding through 256 zero-delay timers, versus
1–12 milliseconds with MessageChannel continuations. The alpha scanner now uses
the latter while retaining exact RGBA reads, bounded tiles and cancellation;
owned ports close in success/error/abort paths. The production build and GPU
alpha/worker cases pass. The isolated stock Firefox cohort then loaded all model tasks in **33.261 seconds**
versus 42.485 seconds before (one observed pair, not a statistical guarantee).
Summed alpha phases decreased from 69.502 to 30.291 seconds; these overlapping
phase durations are not wall-clock loading time. Functional walking/native pose
synchronization and reconnect still passed, but the unchanged fluid gates still
fail at roughly **26 FPS**. Prepared-FBX caching and native draw-state corrections
remain separate pending runtime cohorts. The independent native-state GPU
fixture passed in both engines. The actual Chromium/native-client comparison
passed all five cull/blend/mask/depth cases in both stock engines and verified cleanup of only its four
owned entities. This proves channel dominance and draw-state behavior, not exact
absolute transparent color parity: native linear blending and browser display
blending still differ. Firefox used its actual native-density desktop window;
no public-world resolution setting changed. See the source-bound
[native comparison](evidence/native-render-state-20261001.json).

Next: integrate/test bounded initial ground-support waiting, then the approved
compressed-color material path and separately measured presentation/culling
changes. Refresh actual corrected Kim and strict `overte_hub` after each relevant
runtime cohort; keep Firefox fluid failures and remote asset failures visible. Complete
remaining Tablet/native feature parity, later graphics profiles/options and
resolution percentage, environment recommendations, short stability and measured
optimizations. The user cancelled the 30-minute requirement; it stays cancelled.

## Completed

- Read repository contribution, architecture, source ownership, branch and test guidance.
- Fetched fork `main` and created isolated worktree from `e6ba29f4819fefdc3b212fd00abcf9dbbb6b4999`.
- Validated `feature/main/browser-client`; installed and verified the reviewed branch guards.
- Assigned all three available parallel agents to transport, world, and laboratory.
- Confirmed historical native WebRTC data channels are disabled.
- Implemented browser session UI, real Three.js entity/model/material rendering,
  controls, conservative collisions, standard avatars and object interaction.
- Implemented native session gateway with isolated profiles, private PulseAudio,
  PCM voice bridge, session-owned HTTP(S)/ATP assets and lifecycle teardown.
- Isolated release 2026.04.1 domain, assignments and second native participant run
  locally, without changing existing services or installing system packages.
- Actual browser received seven real entities, native avatar data and rendered
  HTTPS and ATP textured models. Independent screenshot inspection performed.
- Real integration exposed and fixed Quaternion array serialization, native
  null-key duplicate self avatar, and repeated connected-state input reset.
- Fixed native localhost shared-memory domain routing, gateway physics drift,
  clean native departure, and third-person camera obstruction using actual tests.
- Reproducible managed startup provisions real entities and separate binary ATP
  textures, verifies guest permissions, protects HTTP administration, isolates
  domain IPC and audio, and can open the local browser UI.

## Architecture decisions

- Render the world on the visitor device using Three.js, not video streaming.
- Use a per-browser native gateway session to reuse the actual Overte
  protocol, entity decoding, native avatars and audio codec negotiation.
- Leave existing domain services and product roadmap priorities untouched.
- Preserve normal anonymous domain rights. Login-required domains are denied;
  browser account login is not implemented or claimed. Native protocol matching
  is required; current real compatibility evidence uses release 2026.04.1.

## Test evidence

- Branch name checker: allowed.
- Branch guard installation/status: installed, reviewed source matches.
- Production TypeScript/Vite build: passed.
- `npm test`: 52 passed, covering protocol, guest permission policy, self-avatar,
  collision, PCM and bounded audio worklet buffering. The full 52-test suite and
  production build also passed under Node.js 22.23.3.
- `npm run test:browser`: 30 passed in Chromium and Firefox, including actual
  WebGL texture pixels, avatar movement, attached materials, held controls,
  microphone denial/cancellation, clean leave and reconnect.
- `build/repository-checks-env/bin/python tests/run-project-tests.py --profile quick --timeout 240 --junit build/test-results/browser-client-current-main-project-tests.xml`:
  34 passed, 0 failed. This is repository/host evidence, not native coexistence.
- Actual Chromium 153.0.8010.12, stock Chromium 154.0.8037.57, bundled Firefox 155.0 and installed Firefox
  156.0 journeys passed with an independent native participant: actual world
  and asset loading, movement in both directions, collisions, shared interaction,
  clean native departure, mouse look and reconnect. Exact timestamps and tested
  source/bundle hashes are in [VERIFICATION.md](VERIFICATION.md) and its portable
  evidence records.
- Actual bidirectional voice playback passed with synthetic browser microphone
  input and native 997 Hz input. Known-tone measurements were taken from separate
  real native/browser playback outputs; no human conversation is claimed.
- Actual installed Firefox 156.0 physical ALSA capture-device permission/send passed:
  one non-fake live hardware track, 52 frames at 48 kHz, and mute released the track.
  Physical input ports report unavailable; no plugged-in microphone or acoustic
  speech is confirmed. Chromium 153/154 hardware probes exposed zero audio inputs because every
  physical source port reports unavailable;
  that environment limitation is retained honestly in the evidence.
- Actual stock Chromium 154 missing-device UI displayed the clear microphone
  error, kept the real world connected and muted, permitted retry and movement,
  and left cleanly with zero uncaught errors.
- Actual native ArrayBuffer upload and gateway download preserved all 79 bytes
  of a separate ATP PNG texture and its exact SHA-256. The real glTF renderer
  fetched the relative texture. Browser/native screenshots show both actual
  participants; no simulated-world evidence is used.
- A separate actual domain refused native access without exposing world data;
  its administration was authenticated and its fixture used isolated IPC.
- Independently extracted production installation (`npm ci --omit=dev`): passed
  with only two runtime dependencies and zero audit findings. Actual world, native
  peer and binary ATP proof passed. Overlapping leave/repeated gateway SIGTERM
  drained all nine owned descendants, left zero survivors and removed the private
  profile. Final rapid reconnect and bridge-write cancellation regressions passed.
- The user cancelled the 30-minute test on 2026-09-30. It is intentionally omitted.

## Delivery and current work

Implementation and CI/security follow-up commit `53a0d3ac39093ed16490cf2c5a4bd993a06b0141` was published on
`feature/main/browser-client` in the authorized fork; the final lifecycle follow-up
contains the separately verified production deployment and reconnect corrections. [Draft PR #1023](https://github.com/noah-be/overte/pull/1023)
targets `main`; its repository, head and draft state were read back and verified.
At the last unrestricted checkpoint the production UI ran at
`http://127.0.0.1:8090`. Current reachability is unverified under the restricted
platform; the current expanded-scope checkpoint above supersedes this historical
baseline delivery section.

Browser CI on the published head passed both Ubuntu runs: 45 component tests
and 30 actual headed Mesa/WebGL2 browser checks each. CodeQL reports no new
alerts; all three initial findings were fixed automatically without dismissal
or suppression. Workflow security and documentation passed. The complete required repository
run [36736872233](https://github.com/noah-be/overte/actions/runs/36736872233)
also passed, including the full native build/tests and host-project lane; its
successful compiler cache is preserved for the final lifecycle follow-up.

Final production deployment testing exposed and fixed concurrent teardown,
shutdown admission and stale launch state/errors during rapid reconnect. All
callers now await the same cleanup; shutdown refuses new sessions synchronously;
cancelled attempts cannot reset a replacement connection. Independent review,
52 component tests under Node.js 22 and 24, actual production-only deployment
teardown and the final actual stock Chromium 154 and installed Firefox 156
journeys with the native participant all passed.

Delivery requires all exact-head CI gates to pass; their authoritative current
state is recorded on the draft PR. The final lifecycle commit preserves all
existing required repository gates, scanners and test bounds. No long session
test runs. After those checks pass, the next concrete step is review of the
draft PR for integration; authenticated transport and full desktop features
remain explicitly documented later extensions.
The initial repository project, branch, documentation and workflow-security
checks passed. Initial browser CI exposed Ubuntu display/audio prerequisites
and a fixed-delay collision test; actual headed Mesa/WebGL2 and isolated audio
backends now pass all 30 cases locally, with original bounds retained. CodeQL
findings prompted a trusted-configured-origin request boundary and no-input
256-bit native administration token generators. No rules or assertions were
disabled; remote analysis confirmed these fixes on the published head. The final gateway security/lifecycle build
passed the actual stock Chromium 154 journey and focused binary-asset/avatar
checks. No endurance test is authorized or required.

## Updated fork base

Fork `main` advanced to `d569930678d2edb61330a96bcdcab17ee68a732f` during
delivery, integrating existing SafeLanding lifecycle work. The first final-head
repository event carried the old base while GitHub generated a candidate from
the new base; the exact-identity guard correctly refused it before tests. The
current fork base was fetched and merged into this topic without conflicts or
changes to the browser/gateway runtime. All 34 prescribed local quick checks
passed again on the integrated base. Native/build/host gates must confirm the
fresh exact merge candidate; no policy, guard or test is weakened.

## User-added mandatory scope

The user added a fully functional browser Tablet and online world access with
fluid movement, using the actual `overte_hub` as the test world. The earlier
Tablet deferral no longer applies. The active goal remains open. No public
world/server edits or audio broadcast are authorized by a read-only movement
test; isolate native profiles, keep microphone muted and publish only aggregate
participant evidence.

Next concrete step: verify actual public-Hub native admission/permissions/assets
and the native Tablet application's working API. Then implement the required
public browser transport and functional Tablet, measure visitor-device rendering
and walking in the real Hub, and repeat the complete relevant tests. The tested
local anonymous-domain client remains the integration baseline.

The user additionally authorized autonomous implementation/testing of the other
Overte clients' features after all preceding goals pass. The active goal remains
open through that later feature-parity stage. Build a source-derived inventory
and retain honest implemented/tested/externally blocked states; no feature is
removed merely because native parity is substantial.

## Tablet, public Hub and native-worker integration checkpoint

The published `e8c7523a285b688af69955b4baef4ab95660499b` baseline has all
exact-head CI gates green, including the complete native build and 33 native
tests. It is not completion of the expanded user scope.

Actual muted native guests reached the public `overte_hub` using both the local
development runtime and the checksummed 2026.04.1 release. Their actual protocol
signature matches the server. Native address canonicalization required public
admission to bind the actual Domain ID, rather than treating a shareable place
alias as the connection's network identity. Ordinary observed guest asset-write
permission is preserved; no elevated operator identity is inherited.

The real browser now remains connected to the Hub and receives actual entity
records. The first rendering/performance test **failed acceptance**: native
baked material RGB objects were treated as arrays, and Overte's Draco-compressed
FBX geometry was silently empty in the standard Three.js loader. The RGB decoder
is fixed. The bounded FBX adapter now restores actual static Hub geometry,
materials and UVs; real production-browser decoding passed for the bridge and a
multi-material cabana. The latter requires an unmodified, pinned official legacy
Draco decoder because native custom attribute semantics are rejected by newer
decoders. Skinned-model rig/index compatibility remains pending.
Floor stability and fluid movement have not yet passed in the actual Hub.

Browser integration now includes the genuine native Tablet, owned-session frame
validation, pointer/keyboard input and world-input focus separation. Standard
native apps and associated Qt Desktop dialogs have actual capture/input proof;
each full browser app flow and its resulting effects still need verification.
The browser world remains visitor-local WebGL; Tablet frames contain GUI only.
WebGL draws pause while the full Tablet covers the world; physics and replication
continue. Six new renderer checks passed in both browser engines, in addition to
the original 30 browser checks.

Native workers now use private authenticated Xvfb, an isolated filesystem/PID
namespace, sanitized environment and fresh machine identity. Real isolation tests
verify operator-file/environment/PID and sibling-session/display refusal. The
new public network layer adds an outer user/network namespace with slirp, private
DNS and a scoped Unix native-WebSocket bridge. Actual kernel tests passed host
loopback/LAN/metadata route refusal and refusal of guest route tampering. The
real native public join through this network layer passed; its first Tablet
frame still failed the bounded public test and is being diagnosed. A missing
NSS trust-library alternative was fixed and actual native TLS diagnostics now
show neither the missing module nor the previous handshake failures.

Managed local workers now have a bounded relay for explicitly configured domain
and assignment-server UDP ports. An actual isolated-network test verifies exact
datagram bytes and original response address/port while an unspecified host port
receives nothing. Public guests receive no such host exceptions. The latest full
component checkpoint passed 100/100 tests. A concurrent run exposed a real
Python signal-handler/Popen lock deadlock; the handler now only records a signal
flag, with process termination outside the callback. Ten additional actual
abrupt-parent-death regressions passed the unchanged five-second cleanup bound.

Visitor files are cookie-owned and descriptor-bound, with inert download headers,
bounded uploads and symlink refusal. Still-world capture now uses the visitor's
actual WebGL scene even when the Tablet covers it; both Chromium and Firefox
passed pixel checks and refused capture after leaving. Genuine Snap-app PNG/GIF
export and native Tablet navigation effects are being integrated, not yet proven.
The standard laboratory bootstrap now downloads checksummed matching Qt input
modules and a signed user-space network helper, and configures Tablet/public-Hub
prerequisites without installing system services. Its updated integrated start
still needs a fresh actual journey.

The continuation inventory is [FEATURE_PARITY.md](FEATURE_PARITY.md). Required
remaining functions are explicitly pending; showing a native app does not prove
its behavior is reflected in the browser world.

Next concrete step: complete and test actual baked FBX geometry, then repeat the
short real public-Hub journey and measure loaded-world frame time/motion. In
parallel, finish real Tablet app flows and the owned native-worker network path.
No endurance session is authorized.

Further user steering: after the preceding required work, complete Tablet-based
browser graphics profiles/all effective browser graphics options and percentage
resolution, then a browser-environment scan with supported graphics recommendations,
then actual Hub stability testing and autonomous fixes. These are required later
stages, not already implemented or tested. No 30-minute requirement was restored.

The user additionally requires autonomous optimization after the prior stages,
including texture/asset loading and browser rendering. Use measured before/after
results and keep the existing functional/visual/security checks. The active goal
also remains open through this later optimization stage.

## Current integration findings

- The expanded component suite passed 114/114 tests. Both actual managed UDP
  regressions now retain the original cleanup bounds: wildcard-bound domain
  responses are admitted only from the explicitly allowed loopback addresses and
  exact server port, and successful helper EOF no longer races normal owner exit.
- A real isolated native navigation journey passed: a native teleport displaced
  stale browser poses, the independent native participant observed the target,
  an incorrect acknowledgement had no effect, and the exact current nonce
  acknowledgement resumed replicated browser movement.
- The actual Hub bridge and multi-material cabana now have decoded geometry and
  a stable walking surface. Fluid public movement is still **not passed**.
  Measured CPU profiles attribute most long pauses to first-use shader queries,
  rather than FBX parsing or collision construction. Stable light slots and
  asynchronous shader preparation passed 24 renderer checks in Chromium and
  Firefox, but a fresh real Hub profile still reproduced the pauses. Individual
  WebGL query and program-variant measurements are the next diagnostic step.
- The native Snap application exported real visitor-rendered PNG and animated
  GIF files in the managed domain. Full file-management and public Tablet flows
  remain under verification. The public native capture callback completed, but
  its signal-to-WebSocket thread boundary is being corrected; no successful
  public Tablet frame is claimed yet.

Next concrete step: fix the measured shader-query stalls and the native Tablet
signal transport, then repeat short actual Hub movement/reconnect and complete
Tablet app journeys. Later parity, graphics profiles, recommendation scan,
stability and optimization requirements remain active.

The shader investigation found an actual authoring `DirectionalLight` inside the
Hub bridge FBX. The native serializer uses imported lights as asset/lightmap
metadata; it does not add them as domain Light entities. Three.js had rendered
those embedded lights, changing the shader light count for every loaded model.
Imported authoring lights now remain in their transform hierarchy but do not
illuminate the domain. A real glTF extension regression failed before the fix
(19 visible lights instead of 18) and passed in Chromium and Firefox afterward:
three successive models retain the same visible domain-light count and shader
program count, and their actual material pixels remain correct. The production
build passed. A fresh actual Hub movement/native/reconnect profile is running;
its initial streaming samples improved from about 3–6 FPS to about 32 FPS. Final
acceptance still requires the complete profile and replicated motion checks.

The fresh profile finished at 19:54:25 UTC. It loaded all 297 actual models and
75 mesh colliders from 518 domain entities. Shader programs fell from 199 to 25;
program-log queries fell from 57,457 ms total to 83 ms, and no measured WebGL
query exceeded 50 ms. Final streaming performance was 30.1 FPS with 50.2 ms p95
frame time. The native bridge nevertheless disconnected before the walking and
reconnect checks. This run proves the rendering correction, **not completed
public-world acceptance**. The next step is diagnose that native socket/session
failure without extending its existing heartbeat and admission bounds.

## Native transport and loaded-Hub checkpoint

The expanded browser suite passed **52/52** cases across Chromium and Firefox,
including genuinely animated GIF compositor pixels. Its earlier GIF assertion
had received the correct green screenshot but exceeded the unchanged five-second
bound while decoding that PNG inside the already busy browser; decoding the same
captured pixels with bounded Node PNG parsing resolved the test's extra workload.
The expanded component checkpoint passed 124/124 before the latest outbox and
admission regressions were added; the complete new count must be rerun.

Actual bidirectional command traces proved Qt received browser poses, mute,
permissions and Tablet commands while its control-Pong response failed. An exact
nonce application challenge now retains the same 30-second deadline; unrelated
heartbeats do not satisfy it. Native callbacks now enqueue bounded replies for
the Script timer, checking approval, revision and authority again before sending.
Native entity acquisition yields after an eight-millisecond work budget instead
of blocking its event loop for 504–1,036 ms every half second. Its tests cover
ordered snapshots/deltas/deletions, cancellation, revocation and stale timers.

The actual Hub run at **20:20:10–20:21:32 UTC** loaded 298 models, 75 real mesh
colliders and 518 domain entities. Loaded-world measurements reached 41.1 FPS,
33.6 ms p95 and 66.5 ms maximum frame time. Walking moved 4.2136 metres; the
replicated native position differed by only 0.000495 metre. Reconnection still
failed because the previous owned native cleanup retained the one-session slot.
The gateway now waits only for that same cookie owner's already-running cleanup,
then rechecks cancellation, shutdown and the unchanged session cap before any
worker is allocated. Foreign active owners still receive the limit error.

Native opaque FBX part ordering now matches the serializer's first-seen material
buckets. An actual cabana retained all 7,428 triangles, UVs, normals and material
membership with zero rendered pixel changes while its draw groups fell from
three to two. Transparent/uncertain material ordering remains unchanged.

Next concrete step: rerun the complete short real Hub movement/native/reconnect
journey on the coherent frozen gateway, and finish actual Tablet Unicode, Chat,
Places, avatar, Emote, Create and Settings effects. Snap PNG/GIF and visitor
upload/list/download have actual managed-domain proof. An isolated Qt focus
boundary still prevents People text editing and is being corrected. None of
these checkpoints completes the expanded user scope.

## Public Hub acceptance and current Tablet work

The strict actual Hub journey passed at **20:39:49–20:42:03 UTC** using stock
Chromium 154 and the NVIDIA desktop GPU. It loaded 297–298 actual models and
75 mesh colliders from 517–518 entities, walked 4.2131 metres, left cleanly,
rejoined through the unchanged one-session admission limit, loaded the world
again and walked another 2.9027 metres. Native replication errors were
0.000436 and 0.000746 metre. Loaded-world steady samples reached 42–43 FPS,
with 33–34 ms p95 frame times; the cold first window still contains a roughly
one-second stall. The portable evidence is
[public-hub-rendering.json](evidence/public-hub-rendering.json). No microphone,
public entity edits or public audio conversation were used for this journey.

The browser now handles vetted Places handoffs by disposing the previous
world, Tablet, microphone and session before fresh gateway admission. Its
50-entry visitor-local history commits only successfully admitted worlds;
failed or superseded attempts cannot alter the cursor. Seven protocol/history
units and two Chromium/Firefox session-controller component journeys passed.
These component fixtures do not replace the pending real Places GUI journey.

Actual offline native avatar inspection established that the default mannequin
has 69 joints in an order different from its old FST index hints. Rendering
must map the native joint names, preserving model-coordinate translations;
the existing default FBX is uncompressed and does not require baked-skin
decompression. This implementation is in progress.

Next concrete step: complete real Places handoff and Tablet People/Chat effects,
then verify the actual skinned default avatar and Emote animation. Firefox Hub,
the expanded production package, later native feature parity, graphics settings,
environment recommendations, stability and measured optimizations remain open.
