# iOS, Android Phone and Pico feature parity

The owner started this coordinated goal on 2026-10-13 after completing all three
personal-alpha milestones. The goal is the same useful user outcomes in normal
startup on `apple-ios`, `android-phone` and `android-vr-pico`, with controls suited
to touch or VR. A missing app, static web placeholder, disabled working feature
or dormant adapter does not establish parity. Existing stronger features must
remain available.

## Milestone tracking

The current parity work has one milestone per client in the authorized fork:

| Client | Milestone |
| --- | --- |
| iOS / iPadOS | [IOS-P2: Genuine Cross-Client Feature Parity](https://github.com/noah-be/overte/milestone/6) |
| Android Phone | [PHONE-P2: Genuine Cross-Client Feature Parity](https://github.com/noah-be/overte/milestone/4) |
| Pico VR | [PICO-P2: Genuine Cross-Client Feature Parity](https://github.com/noah-be/overte/milestone/5) |

Each milestone records completed source/host implementation separately from
open native builds, remaining integration and fourteen current-artifact device
acceptance criteria. Closing a source task does not establish device parity.
The completed personal-alpha milestones retain their original history. Issue
completion follows the owner's authorization and the evidence for its scope;
the owner explicitly requested the open/closed implementation inventory on
2026-10-13. Future candidate acceptance still needs actual candidate-bound proof.

## Baseline and required outcomes

The source comparison used these exact fork revisions:

| Product | Baseline |
| --- | --- |
| iOS | `0e4c8f96dbab66d5e231c952eb4b3e96b87be3b8` |
| Android Phone | `4df07753d6e86571d77c39f80961d27868b8161f` |
| Pico | `5a907a56a829e3134b8f5f63ff5a309cbbc9ddbd` |

The following requirements remain open until verified on integrated artifacts.
Source wiring and host checks are recorded separately from device acceptance.

The shared QML web callers now execute through the selected native backend;
normal touch startup also loads Create in its own script engine. The registered
`embedded-web-qml` host suite executes the actual tablet and world callers with
Qt Quick, including pre-idle EventBridge traffic, navigation controls, keyboard
transitions, source replacement and Close. It substitutes the native browser
boundary and screen-space IME capabilities; this is not browser/device evidence.

| Feature | Required useful outcome | Acceptance status |
| --- | --- | --- |
| World/navigation | Enter the same reference world, move/interact, use Places and Go To/Back, recover from failed navigation | Pending three-artifact device comparison |
| Account/domain login | Automatic authentication and manual login both open the useful dialog; cancel/logout/restart/domain recovery work | Pico automatic route repaired in shared source; device acceptance pending |
| Avatar/People | Choose URL/bookmark/avatar, scale and wearables; see/connect to the same peers without losing existing capabilities | Existing paths wired; current-artifact comparison pending |
| Create | A normal native entry; create, list/select, edit common and type-specific properties, delete/undo, tools and entity import with permissions and useful errors | Shared native editor and advanced tools tested on host; device acceptance pending |
| Emote | Normal entry, all ten bundled emotes, loading/status, play/stop/toggle, correct teardown and observable avatar animation | Pico startup slice tested on host; cross-client observation pending |
| World HTML | Real document/JavaScript/DOM, pointer/text/scroll, scriptUrl and bidirectional EventBridge; loading/error/navigation/media behavior | Native adapters and shared wiring in progress |
| Tablet HTML | Useful normal browser/app path with history, trusted native interaction/media, packaged apps and EventBridge | Native adapters and shared wiring in progress |
| Graphics | Usable world-effect controls and persistent choices; verify lights, haze, procedural materials and mirrors in the same world | Phone controls tested on host; integration/device effects pending |
| Audio | Mutual voice, playback/mute and permissions/routing; retain live echo and add bounded local recorded/replay/status/cancel on all clients | Shared recorded preview and native-driven UI integrated; device audio acceptance pending |
| Chat/Snapshot | Normal app entries with useful message send/receive/history and actual capture/preview/save/share outcomes | Chat and shared native Snapshot integrated with touch startup; actual Qt5/Qt6 behavior/capture/storage checks pass; platform export adapters and device acceptance pending |
| Scripts/assets | Load/stop/manage ordinary scripts and assets, preserve relative companion files and choose the main file through usable native controls; verify concrete script results and runtime differences | Shared bundle controls and production API bodies pass on host; OBJ parser passes on host; full runtime and device journeys pending |
| Lifecycle/input | Touch/controller/keyboard accessibility, back/close/focus, background/resume/restart, no orphan page audio or stale native input | Per-adapter host checks; three-artifact device acceptance pending |

Performance budgets, rendering resolution and touch/controller mechanics may
differ. They cannot be used to count inaccessible user outcomes as available.
Native and Overte script runtimes also differ: the baseline iOS V8 disables JIT
and exposed WebAssembly. A successful ordinary JavaScript test does not prove
arbitrary WASM-dependent script compatibility. Report actual API/user results
and remaining limits rather than inferring runtime parity from build flags.

## Directory transport

PLACES uses the same sequential asynchronous directory requests for flat touch,
Pico's native page and the desktop web page. Refresh, screen replacement and
script stop invalidate the previous request generation; late responses cannot
replace the current result. Transport errors, timeouts and malformed responses
mark the failed server and continue to the next selected federation entry.
The production-script tests exercise all three UI routes with the transport
boundary replaced. Native control completeness and current-artifact navigation
remain separate acceptance requirements.

## Script and asset bundles

The common native script and asset controls now preserve the selected folder's
relative hierarchy, present a main-file review, execute only the chosen main
script and upload model companions before publishing the primary mapping.
The folder/file operators remain separate; native ownership cancellation retains
the actual request ID. Bundle validation checks real local files and limits
selection to 32 files, 256 MiB per file, 512 MiB total, 1,024 enumerated entries
and 16 relative path components, rejecting aliases and path escapes.

The host checks execute the production dialog caller, relative script resolver,
file validation and upload-batch bodies with actual Qt, local bytes and decoded
images. The host JavaScript engine and asynchronous asset-server peer are
explicit test boundaries. Full V8 execution, live asset mappings, rendered
models and iOS/Android document providers still require current native artifacts
and device acceptance. The separate OBJ parser check executes actual geometry/material parsing and
passes the resulting HFM textures through the material consumer, preserving
nested paths and explicit texture-base overrides. Resource providers and
rendering remain host boundaries; matching transferred bytes alone does not
establish a rendered-model result.

## Ownership and integration

The coordinator owns the common contract, generic UI/startup consumers and
portable APIs/tests. The iOS worker owns the WK backend and iOS integration;
the Phone worker owns the reusable Android native backend in `android-main`
and its Phone adapter; the Pico worker owns Pico startup/input qualification
and the allocated portable native Create work on `main`.

All three client sessions use High reasoning and isolated product worktrees.
Shared/platform work is authored against the highest owning branch. Reusable
Phone graphics is reviewed in a focused `promote/main` branch. Child branches
are never merged upward or into siblings. Follow the
[branch hierarchy and synchronization workflow](../BRANCH_WORKFLOW.md).

## Embedded HTML contract

[`EmbeddedWebPolicy.h`](../../libraries/shared/src/EmbeddedWebPolicy.h) defines
one `overte::web::EmbeddedWebSession` per source-owned surface. It is independent
of the existing contained text-only native view; the original policy stays intact.

- `open(url, surface, sourceIdentity, packagedDocumentRoot)` returns a monotonic
  source generation or zero for an invalid/inactive grant. Hide, foreground
  transition, close and replacement invalidate old generations. Native adapters
  also maintain a document epoch for navigation/redirects and reject old callbacks.
- Ordinary HTTP(S) navigation is available, including cross-origin browsing.
  It never implicitly grants the source bridge to a foreign document. Credentials
  embedded in URLs, privileged schemes and control-character URLs are rejected.
- EventBridge is isolated per surface, current generation/document, originating
  main frame and origin, with a 64 KiB UTF-8 envelope limit. It exposes only that
  page's web/script events. Native app/account QObjects are not registered.
- Use the real `qt.webChannelTransport`, Qt WebChannel protocol and existing
  `eventBridgeJavaScriptToInject` bootstrap. A protocol-shaped stub does not prove
  an Overte web app works. Android providers must report actual frame/origin
  metadata; a frame-blind JavaScript interface is insufficient.
- `scriptUrl` is assigned by the source owner under existing script-consent
  rules. Packaged HTML/scripts use an explicitly approved native-known application
  resource root. Reject path traversal and symlink escape; a page cannot turn an
  arbitrary file path into a resource grant.
- New HTML mode permits the OS-mediated file chooser with explicit user file
  selection in the visible native browser. It does not grant arbitrary app-file
  access. This preserves iOS 17 support without inventing a pre-18.4 public
  file-picker denial API. Native permission decisions remain explicit; existing
  text-only-mode restrictions are not relaxed.
- Tablet presentation must provide trusted native input and ordinary user-driven
  audio/video. World capture uses bounded frames and input tickets. A software
  bitmap or WK snapshot does not prove video-frame compositing. Reference video
  and visible-world input must be tested on the actual artifacts; implement a
  suitable presentation/transport if capture cannot deliver the required outcome.
- Stop, replacement, teardown and background transition must silence/close the
  relevant native page and cancel pending input, composition, bridge and frames.

## Verification and completion

Use the same reference world, accounts/peer scenario and acceptance actions on
all three targets. Do not publish private account/device selectors. Each record
binds the product branch revision, source tree, artifact checksum, build/runtime
configuration, environment, journey outcomes and actual logs/observations.
Separate Debug/E2E from Release and do not replace a user journey with a green
manifest, source-string check or fake native boundary.

The [shared web/media reference](../../tests/device/fixture/parity/README.md)
provides identical original video/audio, DOM/input/navigation/file-choice and
real EventBridge echo content for the world and tablet. Its checked media bytes
and HTTP streaming tests qualify the input. The listed visual/audio/actions
must still be observed on each exact client artifact; they do not establish
device acceptance by themselves.

The shared policy has a compiled host regression:

```bash
python3 tests/device/contracts/web/test_embedded_web_policy.py
```

The [project runner](../../tests/PROJECT_TESTING.md) registers it in the host
profile. Run relevant behavioral/QML/backend checks and the required quick
profile before proposing integration. Native client builds and device journeys
remain separate requirements. The
[mobile graphics guide](MOBILE_GRAPHICS.md) is added by the focused parent
promotion before this dependency is integrated.

The coordinator may claim complete feature parity only after every requirement
above is implemented, available through its real caller and verified at the
appropriate scope on all three exact artifacts. A successful preparatory slice
does not complete this goal. Further GitHub issue completion requires the
owner's authorization.
