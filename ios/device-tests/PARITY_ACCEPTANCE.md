<!-- Copyright 2026 Overte e.V. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Current-artifact iOS parity observations

This supplements existing device procedures for IOS-P2 criteria
[#1164–1177](https://github.com/noah-be/overte/milestone/6). It does not replace
their acceptance conditions, historical evidence or stronger client features.
All fourteen current-artifact journeys are **not performed** by this preparation.
The reviewed implementation baseline is
`fc9bc126a0900b980b056291231f3b28786fcfb9`; it is a host checkpoint, not a
selected native candidate or installed IPA. Use the
[blank observation sheet](PARITY_OBSERVATION_TEMPLATE.md) only after the
coordinator selects the actual candidate and owns the laboratory slot.

## Bind every observation before interpreting it

Record full producing source revision, source tree and ordered parents, separate
PR head/merge identities where applicable, build configuration, producing
workflow/run/attempt, Qt/Xcode/iphoneos SDK/deployment floor, exact IPA size and
SHA256, package-verification receipt and any subsequent signing derivation.
Join this to a verified installed-code identity and observed version, anonymous
device reference, actual iPadOS version/build, process/session continuity, test
runner revision, fixture hashes and UTC start/end. Every evidence item needs a
step identity, original private path, SHA256 and its contemporaneous observation.
Keep credentials, device selectors, signing identities and private account data
out of public notes. Compare the same controlled scenario on the other clients.

An archive checksum or visible version label alone cannot establish which bytes
are installed. The separate optional canonical
[`tests/device/adapters/ios/binding.py`](../../tests/device/adapters/ios/binding.py)
deliberately withholds `executionIdentity` and rejects session/invoke with
`OVT_IOS_INSTALLED_CODE_BINDING_UNAVAILABLE`. Its candidate preflight is not
installed-code verification. The existing
[personal-team route](../../tests/device/ios/README.md) explicitly describes
Sideloadly's `none-device-observed` handoff and lack of cryptographic association
with rewritten installed bytes. Do not silently turn that limitation into the
strict source/IPA binding required here. Record **not bound** and ask the
coordinator to resolve the owning contract before claiming strict candidate
acceptance through that optional bound path.
This preparation neither changes the binding gate nor selects a signing method.

The actual Jenkins path is `run-full-e2e.py` →
`wifi-runtime/adapter_daemon.py` → `WifiAdapter(IOSAdapter)` through a private
adapter socket. It does **not** select `appium/ios-bound.json`, pass
`--native-binding` or call the above binding module. The optional stub therefore
does not block the existing observation-only lab run. Its rejection must still
remain intact for an explicitly bound run. The active path itself retains
`cryptographicInstalledByteBinding=false`; availability of real operations
does not establish the stronger identity claim. Existing historical results
stay attached to their original artifacts. Record supplemental manual results
with their actual provenance limits, never as an exemption or full bound result.

## Existing laboratory coverage, inspected read-only on 2026-10-13

Use the [Jenkins CLI workflow](../../tests/device/jenkins/README.md) and existing
exclusive laboratory ownership. `overte-jenkins help`, `list-jobs` and `get-job`
were read; no job, installation, app or device action was started.
The `overte-ipad` entry offers `RUN_MODE=readiness|full-e2e|focused-e2e`,
`MODULE_IDS`, and `RESUME_BUILD`. Focused IDs must come from the selected actual
catalog. This entry does not itself expose source/IPA pin parameters.

The inspected default immutable lab runner is
`996b3c90799b1b42403a50e69778a5b99ba85241`; its 35-module catalog SHA256 is
`3c2f7d546cd34868764885018dc7c62b677712deb9fd18c89412b9962fbb5cab`.
This describes the default configuration, not the environment of an executed
run. Freeze the runner actually selected for the future session separately.
The current repository's [common catalog](../../tests/device/catalog.json)
also contains 35 modules. The small local [universal catalog](catalog.json)
has two launch/stability entries and does not replace the full native runner.

The source selection and most recent retained run were also inspected without
contacting the device. They are historical, not current installation discovery:

| Retained fact | Value and boundary |
| --- | --- |
| Installation record and selected producer manifest | Build `756`, source `f8f9ff33d515f7743159883544b4f02a250d4412`, status `installed-and-vm-stopped` |
| Unsigned producer IPA | SHA256 `bb05493ad6358ef57a6cacf2fbae02b4afecece8a15cef1bf5d61ba07226c3ad`; Release/arm64/iphoneos, SDK `26.5`, Xcode `26.6` build `17F113`; signing still required |
| Latest retained lab summary | Run `152`, UTC `2026-10-10T11:05:56.546617+00:00`, same build/source/unsigned hash and immutable runner above |
| Retained native preflight | iPadOS `26.7`, physical device/profile checks; `cryptographicInstalledByteBinding=false` |
| Retained summary bytes | SHA256 `846c41de11918aaee53faa3c89635d1442d73322b8d839a4b316439b540f58bc`; kept in the existing private lab run, not rewritten here |

`wifi-runtime/observe_preinstalled.py` validates the private selected installation
record against the producer manifest and uses authenticated InstallationProxy
inventory for bundle/executable/version, profile validation, signer/team,
entitlements and declared E2E feature markers. The active native process path
observes the actual PID, executable identity and foreground continuity. These
are useful OS observations, distinct from app-generated telemetry. Neither
inventory nor PID supplies an executable/CodeDirectory hash. The retained
installation record contains the unsigned input SHA256, not a verified final
signed IPA or observed installed-code digest. Its signing derivation is explicitly
human-verified. Documents/probe data and an app self-report cannot repair that
cryptographic gap. No current OS version, candidate association or new result is
inferred from these older files.

The native iOS binding module and iOS signing/install observation helpers are
iOS-product-owned. A future implementation must join a reviewed final signing
derivation and independently observed running-code identity to the pinned
candidate before emitting `installedCandidateVerified=true`. Investigate that
mechanism separately in the reserved native slot; do not invent a digest from
bundle/version equality or modify the active observation-only receipt to claim
more than it establishes. This document implements no installation or binding.

| Existing mechanisms | Useful supporting observation | Coverage boundary |
| --- | --- | --- |
| `scene`, `domain-enter`, `domain-roundtrip`, `look`, `move`, `world-interaction`, `app-restart` | Controlled scene, motion, interaction, recovery | Does not qualify Places UI or account login automatically |
| `tablet-e2e`, `text-input`, `accessibility`, `tablet-input-isolation` | Actual controls, input/focus and tablet transitions when advertised | Existing control vocabulary is not a complete semantic model of every new app or WK document |
| `voice-roundtrip`, `audio-controls`, `permission-recovery`, `sound-playback` | Owned peer challenges, mute/permission state and playback | Does not establish every route or the new recorded-preview UI by itself |
| `asset-load`, `scripted-entity`, `entity-sync` | Controlled texture delivery and scripted/entity effects | Not the normal Scripts manager, folder companions, OBJ rendering or real asset-server mutations |
| `render-health`, `lifecycle-under-load`, `lifecycle-soak` | Process, native presentation and general foreground health | A nonblack scene or frame counter is not moving video within a world Web entity |

The iOS [native adapter](../../tests/device/ios/adapters/adapter.py) has gated
operations for fresh process/foreground, command-correlated client probe,
native UIKit tablet observations, text and render observations, permissions and
controlled collaboration. Capability advertising depends on the actual target
configuration; it must be checked after binding, not assumed from source.
`native_render_snapshot` supplements presentation counters with central-world
screenshot pixels, but does not identify the web video's rectangle or frames.
The [acceptance observer](../../tests/device/ios/ACCEPTANCE.md) reports renderer,
scene, avatar, window, native audio and touch metrics; it has no complete SNAP,
script-manager, document-provider or web-video completion contract.

An advertised `artifact.screenshot` saves `screenshot.png` and overwrites it in
the same artifact directory. Reserve distinct private step directories and
retain original files/hashes. UI screenshots and observer samples support actual
visible outcomes; receiving a valid JSON document does not pass a journey.

## Fourteen normal-entry journeys

Use the ordinary installed client entry and platform-appropriate touch/keyboard.
Only manipulate the controlled test world's entities, server mappings and peer
scenario assigned to this run. Keep a before/action/after record with visible
results, errors/cancellation and cleanup. Missing prerequisites remain blocked or
not performed, not passed. A failed negative control is a failure, not coverage.

| Issue | Actions through the normal client | Required visible result and evidence |
| --- | --- | --- |
| #1164 World/navigation | Enter reference world; move/look/interact; use Places and Go To/Back; enter invalid destination and recover | Same world landmarks and actual movement/interaction; useful failed-navigation state followed by recovery. Join scene/process samples to display evidence. |
| #1165 Authentication | Automatic prompt and manual account/domain login; wrong test credential, Cancel, successful login, Logout, restart/reconnect | Both actual dialogs appear; correct accepted/denied state, cancellation and no stale authenticated session. Record sanitized states, never credential fields. |
| #1166 Avatar/People | Choose controlled avatar by URL and bookmark; change scale/wearable; see and connect to the same peer | Actual changed avatar/scale/wearable and peer state on both clients, retained choices where expected, useful unsupported/denied errors. |
| #1167 Create | Normal Create entry; primitive and model/image; list/select; common and type-specific edit; delete/undo; an advanced tool/voxel operation and entity import; denied role | Actual world geometry/properties and successful undo; real type/tool outcomes; denial causes no unauthorized mutation. Record entities only within this run's temporary scope. |
| #1168 Emote | Normal Emote entry; exercise each of the ten bundled animations, Play/Stop/toggle, then close/reload | Loading/status and visible avatar motion for each animation; correct stop and no duplicate handlers or continued playback after teardown. |
| #1169 World HTML | Normal Web entity with the shared reference; pointer/text/scroll, assigned scriptURL, real echo, navigation/Back/Reload, media and close | Real document and bidirectional script echo, source-origin rejection/restoration, actual encoded MP4 pixels within the world plane. Follow the focused world procedure below. |
| #1170 Tablet HTML | Normal tablet/browser and packaged app; same reference page; native input/chooser/media, history and echo | Visible native document/app, real keyboard/file return, media pixels/tone, actual same-origin echo and foreign-origin rejection. Tablet success cannot pass world pixels. |
| #1171 Graphics | Normal graphics controls; change and persist choices; observe controlled lights, haze, procedural materials and mirror | Usable UI and real corresponding world effects; restore/restart confirms persistence. A changed setting value or nonblack screenshot alone is insufficient. |
| #1172 Audio | Mutual peer voice; mute/unmute; microphone deny/grant; available device routes; live echo; bounded record/replay/status/cancel | Actual peer sound and negative mute control, route/permission outcomes and local replay of fresh captured sound. Use existing acoustic/voice procedures; silence, clipping or preview cancellation failures are explicit results. |
| #1173 Chat | Normal Chat; Unicode send/receive with same peer; close/reopen; restart and retained bounded history/preferences | Real peer receives and replies, proper displayed order/history/settings, usable keyboard and no duplicate deliveries after teardown. Local echo alone cannot pass network Chat. |
| #1174 Snapshot | Normal SNAP; still, animated GIF, panorama and cubemap; preview, save/share, permitted upload/audience; cancel/error/lifecycle | Actual current world image files and previews, real native completion/errors, retained original captures and truthful cancellation. Use focused export procedure below. |
| #1175 Scripts | Normal Scripts; ordinary URL and native local file; native folder bundle/main selection; observe, restart/stop, cancel/error | Real script-created world result and teardown; preserved relative companions execute in real V8. Listing a script or copying files alone does not pass. Use focused provider procedure below. |
| #1176 Assets | Normal Assets; read-only browse, permitted image/model rez, folder companions, upload/mapping rename/delete/baking, denied role | Actual rendered object/image and material/texture, verified server mutations only in owned namespace, complete companions and truthful failure/cancel count. Use focused asset procedure below. |
| #1177 Lifecycle/input | Back/Close, focus changes, software/external keyboard, orientation/window changes, background/resume/restart and pending native operations | Usable geometry/focus and neutral input; no stale callbacks, retained unexpected sheet, orphan voice/page audio or capture; expected process continuity/restart correctly recorded. Repeat with browser/provider/export work pending. |

## World and tablet media (#1169/#1170; open #1179)

Follow [WORLD_VIDEO_ACCEPTANCE.md](../web/WORLD_VIDEO_ACCEPTANCE.md) and the
unchanged [common reference](../../tests/device/fixture/parity/README.md).
Keep the world plane and surrounding geometry visible. Observe at least three
full loops of encoded red/green/blue movie frames, changing encoded numbers and
white-square position, Pause/Seek-to-blue/Resume, and real DOM/bridge/input.
Use the same MP4 bytes, URL and IPA in the native tablet control. Do not inject
a canvas replacement, alter media policy, or promote `currentTime`, DOM motion,
audio or fullscreen native playback into a world-texture pass. If a screenshot
omits motion seen on the physical display, distinguish recorder omission with
external camera evidence before attributing it to the renderer.

## Files, folders and actual script execution (#1175/#1177)

Use [the native provider contract](../documents/README.md). Prepare controlled
nonprivate local Files content and a real cloud/document provider. Exercise one
file, unique sibling files, duplicates, folder selection with nested companions,
user Cancel and visible provider/read failures. Successful copies must retain
original names, bytes, hierarchy, hidden/empty directories and durable readability
after dialog destruction and app restart. A returned scoped URL is not a durable
app copy. Distinguish a chooser's normal inactive transition from backgrounding.

The limits are 32 files, 256 MiB/file, 512 MiB total, 1,024 entries and 16 relative
components. Boundary violations, aliases/symlinks, collisions and unreadable or
vanishing children must fail the whole selection without exposing partial files.
Repeat Cancel/Close/background while materialization or copying is pending;
confirm the original request's terminal result and no stale result on a new one.
Use provider-controlled test data rather than changing operating-system security.

For real execution, load the existing common `webParity.scriptUrl` normally and
verify its local Web entity, `WEB TEST` entry, native script echo and scriptURL
injection. Restart it without leaked entities/handlers; Stop removes its own
entity/button and callbacks. For the nested script case, a versioned companion
bundle must have a known main file and `Script.include`/relative require whose
result visibly changes the world. Record the input manifest/hashes and the
actual result, then restart/stop and reopen the retained copy. The missing
portable companion fixture is a Main-owned proposal below, not invented test
input already distributed by this branch. Ordinary JavaScript success does not
certify WebAssembly: iOS V8 is JITless and does not expose Wasm.

## Asset companions and server results (#1176)

Select the real folder and main OBJ through Assets' bundle review. The controlled
bundle must include nested MTL/texture paths, distinct materials sharing a texture
basename, a decoded known-color PNG and an explicit FST texdir case. Compare the
complete input hierarchy and hashes with the durable app copy and, for upload,
the actual server mappings/downloaded original bytes. Observe actual world model
geometry and intended texture colors. A returned entity ID, parser output or
mapping count is not rendered-model proof.

Run first as read-only, then with the assigned writable role and unique test
mapping prefix. Inspect companion-before-primary publication and actual final
primary URL; rename/delete/bake only this run's owned content and observe server
results. Cancel/failure may leave already published mappings: the UI count and
actual namespace must agree rather than claim complete rollback. Record missing
companion, unavailable server, denied rez/upload and provider failure visibly.
The shared host fixtures are useful prerequisites, not live asset-server or GPU
evidence. A portable real bundle/server scenario still needs owning Main input.

## Snapshot native export and original bytes (#1174/#1177)

Open normal SNAP and select `Still`, `Still + animated GIF`, `360° panorama` and
`360° cubemap`. Use a known moving scene for GIF and known directional landmarks
for 360 captures. Observe capture/processing/complete status and real previews.
Inspect original authorized app capture files: format/dimensions, nonempty decoded
pixels, multiple changing GIF frames/delays and correct panorama/cubemap coverage.
Do not create a thumbnail or text placeholder and call it a capture.

Use `Save to device` and `System share` in the review, following the
[native adapter contract](../snapshot/README.md). Test add-only Photos denial and
grant, real transaction completion, visible media in Photos, iPad share popover,
user cancellation and an explicitly selected controlled receiver. Verify the
receiver's actual file when testing its storage outcome. A completed activity
controller reports sharing completion, not that every recipient stored bytes.
Original app files remain available after still/GIF/360 export; retain their
hashes independently of any Photos derivative or receiver transformation.

With the assigned account/role, explicitly choose `Upload for URL` and permitted
audience actions. Verify the actual URL/story and audience result; do not publish
test snapshots to a public audience without the coordinator's chosen scenario.
Cancel capture, GIF processing, upload and system export, then close/replace or
background. A Photos write already committed may finish successfully after a
cancel request; record that result honestly. Observe busy-lease return, exactly
one current terminal outcome, no stale update in a new review and no deletion of
original captures. Inspect export errors; absence of a prompt is not successful
save. Existing native sheets are not assumed to expose semantic test IDs.

## Bounded owning-Main proposals; no implementation here

1. **Portable companion input:** extend `tests/device/fixture` with a reviewed
   ordinary nested-script bundle and OBJ/MTL/PNG/FST bundle plus exact manifests,
   preserving names and known visible outcomes. Reuse existing parser fixtures
   as design evidence; do not mistake generated host temporary files for a
   distributed native-runtime diagnostic.
2. **Product observations and catalog:** allocate separate bounded modules in
   `tests/device/catalog.json`/`modules` for real browser media, native export and
   normal Scripts/Assets outcomes. Inspect `tests/device/probe/overte_e2e_probe.js`
   and existing versioned operation contracts before proposing narrowly scoped
   additions for current operation/request, terminal state, selected resource
   identity and completion. Keep byte/visual/server observations independent;
   neither a page-generated success message nor native presentation counts pass
   movie pixels or receiver persistence. Add no account/native-object exposure
   to web EventBridge. Native UIKit or platform observation adapters follow their
   owning parent/client after common contract review.

Until those routes are real and candidate-bound, retain the supplemental manual
worksheet and mark automated portions **not covered**. A full existing catalog
result cannot silently inherit the fourteen product-level acceptance results.
The user controls issue completion; this preparation performs no GitHub write.
