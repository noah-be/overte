# Browser feature parity inventory

Material implementation assistance: OpenAI Codex. This inventory implements the
user's 2026-09-30 instruction to continue autonomously after the initial client,
functional Tablet and actual online-Hub acceptance. No item is removed because
it is difficult or requires a separate native/browser integration.

The comparison target is the native functionality in this topic's current fork
base, `d569930678d2edb61330a96bcdcab17ee68a732f`, and the compatible native runtime
used for each actual test. A native UI shown in the Tablet does not establish
that its effects work in the visitor's browser world. Each item needs behavioral
evidence, including the resulting world/avatar/audio state where applicable.

The latest user instruction restricts subsequent browser tests to Google Chrome.
Retained Firefox/Chromium results describe their tested historical versions;
they do not authorize additional Firefox launches. Thirty-minute/endurance tests
remain cancelled.

## Source entry points

- `interface/src/Menu.cpp` and `Menu.h`: desktop navigation, accounts, editing,
  preferences, developer tools, rendering, assets, avatar, network, audio and
  physics controls.
- `scripts/defaultScripts.js`: standard applications and controller behaviors.
- `scripts/system/tablet-ui`, `scripts/system/more`, `scripts/system/places`,
  `scripts/system/create`, `scripts/system/avatarapp.js`, `audio.js`, `pal.js`,
  `snapshot.js`, `emote.js` and `armored-chat`: installed Tablet applications.
- `interface/resources/qml/hifi/tablet`: native pages, preferences, dialogs,
  model browsers, avatar packaging and device configuration.
- `libraries/entities/src/EntityTypes.*`, `EntityItemProperties.txt` and
  `libraries/entities-renderer`: native entity types, materials and effects.
- `libraries/script-engine` and exposed scripting interfaces throughout
  `libraries`/`interface`: script execution, API permissions and event behavior.
- `scripts/system/+android_interface`, `+android_phoneInterface` and the
  display/input plugins: mobile, controller, tracking and VR behavior.

## Acceptance inventory

“Baseline verified” refers to the published initial functional proof; new
additions require fresh evidence on the integrated version. “In progress” and
“Pending” are not passing states.

| Function | Browser status | Required behavioral evidence |
| --- | --- | --- |
| Join, leave, reconnect, session isolation | Baseline verified | Real native coexistence and cleanup |
| Managed anonymous-domain rights | Baseline verified | Native/configured permission agreement and refusal cases |
| Actual public online places and Hub | Current default-quality Chromium and Firefox short Hub residence journeys pass all four original fluid/native/reconnect gates. The default-off template Firefox comparison retains its freshness failure; no cache speed gain is established. Historical low-FPS failures remain retained | Guest admission, real assets, native pose agreement, reconnect |
| Directory browsing, bookmarks, history, paths and portals | Genuine Places seven-handoff journey verified; departure viewpoints and portals follow-up open | Actual destination changes and saved visitor preferences |
| Account login, domain login and logout | Pending | Normal identity/admission preserved without operator credentials |
| Domain capacity, bans, source-IP and fingerprint policies | Pending | Actual supported identity transport and refusal behavior |
| Real primitive geometry, GLB/glTF, FBX, OBJ and FST | Baseline verified; Hub extensions in progress | Actual asset geometry and visual checks |
| ATP and HTTPS assets | Baseline verified | Actual native ATP bytes and relative texture rendering |
| Baked FST materials and texture metadata | Actual Hub static assets verified; remaining formats pending | Actual Hub FBX/material/image rendering |
| Material layers, texture transforms, PBR and advanced materials | Pending | Source-specific rendering comparisons |
| Zones, skyboxes, ambient light, haze and bloom | Prepared unintegrated Zone module has 27 unit passes; native ambient/shadow adapter and GPU proof pending | Actual native scene comparisons |
| Shadows, ambient occlusion, LOD and graphics preferences | Pending | Browser effect, measured performance and persistence |
| Procedural shaders and custom material shader execution | Pending | Compatible shader semantics and permission boundary |
| Particles, polylines, polylines' textures and polyvox | Pending | Actual dynamic content and authored properties |
| Web entities, overlays, canvas and embedded web applications | Pending | Input, event bridge and isolated content permissions |
| Dynamic entities, animations and actions | Pending | Actual authoritative simulation and visual updates |
| Keyboard/mouse/touch movement and view | Baseline verified | Actual motion and view controls |
| Static mesh and compound collisions | Actual static mesh Hub walking verified; compounds pending | Actual Hub walkable geometry without bounding-volume traps |
| Flight, sitting, teleport, navigation and camera modes | Pending | Native/browser pose ownership and working controls |
| Self and other participants' visibility | Baseline verified with capsule fallback | Actual shared native movement |
| Avatar models, FST rigs and attachments | Original default FBX rig verified; selections/attachments pending | Actual selected avatar assets and native/browser agreement |
| Joint poses, animation, emotes and facial blendshapes | Pending | Visible native/browser rig and animation agreement |
| Avatar scale, preferences and avatar favorites | Two fresh actual native workers restored persona; genuine GUI persistence follow-up pending | Resulting browser rig and persisted visitor choices |
| Bidirectional native voice, mute and playback | Baseline verified using synthetic input | Separate actual native/browser playback captures |
| Physical microphone voice | Unavailable in the historical baseline environment; current host exposes one hardware input, actual Chrome/native capture pending | Actual microphone/input test; no synthetic substitution claim |
| Audio device, gain, spatial mix and audio preferences | Current Google Chrome native Tablet EC/NS/AGC toggle and restoration effects verified; gain, device choice and remaining mix/preferences pending | Actual browser/device effects and native mix |
| Entity sounds, audio injectors and local playback | Pending | Actual source position, media and permissions |
| Fully functional standard Tablet | In progress | Genuine apps, pointer/keyboard/text input and resulting effects |
| Audio, Shield, Snap, Avatar, People and Chat apps | In progress | Each app's complete relevant user flows |
| Places, Create, Emote, Settings and More apps | In progress | Each app's complete relevant user flows |
| Additional app installation and lifecycle | Pending | Normal native app behavior inside visitor isolation |
| People, connections, ignore/mute and moderation | Pending | Actual participant controls preserving granted rights |
| Chat, nametags, notifications and status | Actual two-participant Chat verified in both engines; remaining behavior pending | Actual native/browser communication and visibility |
| Snapshots, recording and browser file download | Actual Snap PNG/GIF (5,000 ms) and file transfer verified in both stock engines | Visitor-local world capture and usable exported files |
| Create/edit/delete/clone, selections and transform tools | Pending | Actual isolated-domain edits observed by native peer |
| Entity property editing, scripts and interaction events | Basic click interaction verified; editor pending | Authoritative changes with normal entity ownership |
| Asset browser, upload/download, baking and model packaging | Pending | Actual asset workflow with private visitor workspace |
| Script console, running scripts, APIs and script consent | Pending | Genuine execution and effective sandbox/consent checks |
| UI file dialogs, clipboard and persistence | Pending | Visitor-owned files/preferences; no host credential exposure |
| Browser session native-worker filesystem/process/display isolation | In progress | Cross-session and operator-data refusal checks |
| Developer diagnostics and logs | Baseline read-only diagnostics; further tools pending | Accurate actual renderer/network/physics measurements |
| Controller, gamepad, keyboard remapping and accessibility | Pending | Actual browser inputs and persistent configuration |
| VR/WebXR, tracked hands, HMD and controller interaction | Pending | Browser implementation and actual compatible-device proof |
| Mobile/phone/Pico-specific journeys | Pending | Relevant actual-device validation with version-bound results |
| Production distribution, self-hosting and meaningful CI | Baseline verified | Fresh production build and exact-head gates after additions |
| Tablet browser graphics profiles and all effective options | Seventeen genuine native control/profile effects and thirteen painted-popup checks verified in both stock engines; additional native rendering effects remain pending | Every control changes the actual visitor renderer and persists appropriately |
| Render resolution expressed as a percentage | Actual100/80/60/Custom70% framebuffers and leave/rejoin persistence verified in both stock engines | Actual framebuffer dimensions and image/performance effects |
| Automatic environment scan and graphics recommendations | Actual unchanged-settings Scan/hidden/leave/rejoin passes in both stocks. Both sampled views recommend retaining settings; optional Apply GUI remains pending | Actual browser capabilities/performance, explained recommendation and explicit apply |
| Final actual online-Hub browser stability and autonomous repairs | Pending; after preceding goals | Reproducible short stability journeys, measured stalls/errors and verified fixes |
| Texture/asset loading and rendering optimization | Immediate priority after joining, explicitly advanced by the user; measured cohorts in progress | Measured load/frame-time improvements with unchanged functional and visual checks |

## Current next step

Optimize cold world/texture loading immediately after joining, correct measured
Chrome loading/rendering stalls and complete remaining Tablet
app effects, including fresh-profile Places Bookmark/Home restoration, selected
avatar appearance, native Emote animation, Create and Settings.
After that acceptance, continue through the remaining rows and expand them into
source-specific checks. Keep the active goal open while required work remains.
The user cancelled all 30-minute/endurance testing; use meaningful short journeys.
