# Browser client implementation plan

## Immediate independent-review follow-up (2026-10-03)

The existing browser implementation owner is fixing the two confirmed defects
reviewed at `261fc77c1c322410f6096e65dcff0388c372286d`: retain Tablet command
ordering across same-worker reapproval, and bind prepared FBX cache delivery to
the captured asset approval and revocation epoch. Keep stale/replayed commands,
reader cancellation, deduplication and all resource limits enforced. Qualify a
narrow source snapshot with actual-handler CPU regressions. The user authorized
a local committed review checkpoint while full-suite/build/repository checks
wait for the shared heavy-build lock. Return its full SHA with those gates
explicitly pending, then complete them under the lock before publication.
This handoff does not trigger a live/native/device journey, restart services,
change issue state or publish the PR. Subsequent browser work uses Chrome only;
thirty-minute/endurance tests remain cancelled. Existing source-bound live
qualifications remain historical until reconciled with the changed source.

Material assistance: OpenAI Codex. This is the user-authorized browser project,
independent of the existing product roadmap.

Topic: `feature/main/browser-client` in the separate browser-client worktree.
Initial fork main: `e6ba29f4819fefdc3b212fd00abcf9dbbb6b4999`; subsequently integrated
reviewed fork main `d569930678d2edb61330a96bcdcab17ee68a732f` for coherent CI ancestry.
Only `noah-be/overte` is authorized for GitHub writes. Verify exact repository
ownership and rewritten push URLs before every mutation; upstream remains read-only.
Preserve other worktrees, credentials, hooks, existing services and unintegrated branches.

## Mandatory scope and ordering

The user cancelled all thirty-minute/endurance testing. Do not reinstate it.
The durable unbudgeted goal remains active until every required stage is proved.

1. Deliver real browser-side world rendering, domain selection/admission/leave,
   HTTPS and ATP assets, keyboard/mouse movement/collision/interaction, native
   avatar synchronization, bidirectional native/browser voice, useful errors,
   reconnect, production distribution and free self-hosting. Test actual native
   and browser participants in the isolated domain with short functional journeys.
2. Complete the genuine browser Tablet and fluid online-world movement in the
   actual `overte_hub`, in stock Chromium and Firefox. Preserve normal guest
   admission and rights; public testing remains muted and read-only.
3. Inventory, implement and test the other native clients' remaining features.
   Hardware absence or unsupported content must never be represented as a pass.
4. Expose every supported effective browser graphics option through the Tablet,
   useful explicit profiles, and render resolution as a percentage. Scan actual
   capabilities and representative loaded-world measurements to recommend
   settings; explain uncertainty and require the visitor's explicit application.
5. Run short real Hub stability journeys and correct measured errors/stalls,
   then continue systematic texture/loading/rendering optimization.

The user's immediate priority overrides the later optimization ordering:
**speed up world and texture loading immediately after admission now**. Continue
this alongside current Tablet/Hub acceptance, without lowering visual quality,
rights, resource bounds or the unchanged fluidness thresholds merely to obtain a pass.

## Architecture and decisions

Historical Overte data channels are disabled; WebRTC audio is not a browser
transport. Reviewed Vircadia Web/Web SDK require corresponding server channels
and protocol compatibility. The implemented route is Three.js rendering actual
entity/asset data on the visitor's device, through a self-hosted native-protocol
session gateway. Each visitor has its own isolated native process and authority.
Native Qt Tablet applications are reused with exact reviewed per-session adapters.
Managed domains and operator-approved public guest domains have distinct paths;
no arbitrary-public-domain or authenticated-domain compatibility is promised.

Every cache has bounded storage, actual cancellation, visitor/session ownership
and permission-generation checks. Models can publish genuine collision geometry
before textures finish. Prepared FBX, decoded image sources, embedded images,
approved native compressed color textures and source text are reused without
sharing mutable materials or weakening admission. Native-only/uncertain effects
remain reported until genuinely implemented and verified.

Graphics start at100% of the initial device density capped at2. No recommendation
silently changes it. Default-off rendering/resource experiments require actual
pixels, functional acceptance and a meaningful Hub measurement before activation.

## Current evidence and next concrete work

Current next steps: qualify genuine Desktop PTT/People/Sit and the exact hosted
bootstrap fixes, then measure the default-off dispatch observer in the actual
Hub and fix measured rendering/texture bottlenecks. Published checkpoint
`6389ab139436e78e73ce616c3ffe0a104f2b69d9` and draft PR1023 are verified.
The subsequent production build and1,551 registered components pass with zero
skips. Exact diagnostic-on/off WebGL2 pixels and all original registered
assertions pass in stock Chromium154 and Firefox156; this is an authored
fixture, not Hub performance evidence.

The measured prepared-cache128 Hub comparison reduces repeated preparations
and eliminates count evictions at unchanged128MiB payload/8MiB key bounds.
Image transfers are unchanged; Chromium passes all four fluidness gates while
Firefox still fails three. Native-ignored FBX pruning remains qualified by
zero-tolerance original production-worker images in both engines. The earlier
rendered-light-prefix candidate remains rejected outside production.

Actual reciprocal native People geometry and synthetic audio pass in Chromium;
Firefox's portable driver correction remains unqualified after a later genuine
stale-frame refusal. The bounded browser-owned PTT witness queue passes41 CPU
contracts, and actual held/released key/native-output gates pass in both stocks.
Their next reverse-audio stage fails because the copied harness omits the
independent native peer's explicit unmute, unlike the original core journey.
A source-bound owned peer-command/readback/restoration followup is required;
no runtime receive bug or complete PTT result is claimed. Exact Emote Sit
adaptation passes10 CPU contracts; genuine native Sit/key Stop remains pending.

Exact hosted6389 failures identify python-import-alias-target/errno13 and
keyring-write-permissions. Narrow canonical-alias hashes/literal read policy
pass all82 Root C/Python contracts, retaining original boundaries. The pinned
Ubuntu-package/private-keyring bootstrap passes all67 Root CPU contracts and
the genuine cached archive signature chain. Both await actual hosted proof.
Preserve the original2800ms native peer movement deadline, reset the actual
owned author pose freshly before its next passive original journey, and keep
physical microphone acceptance distinct from authored synthetic input.

See [STATUS.md](STATUS.md) for exact published commits, actual source-frozen
cohorts, preserved failures, tests and remaining limitations. Original real
native/browser journeys passed in both stock engines, including synthetic voice
in both directions; no physical-microphone conversation is claimed. The expanded
Tablet/native-parity and Firefox fluidness requirements remain incomplete.

The current source-text and graph-memo checkpoints reduce actual repeated Hub
metadata requests/inspections while retaining exact approval ownership. Prior
stock engines synchronize and rejoin, but the latest measured Firefox fluidness
and Chromium reconnect stall remain unresolved. Default-off shader and foreground
texture preparation now pass actual exact-pixel/resource tests in both bundled
engines. Neither candidate has established a whole-Hub speed benefit.

The genuine native Graphics popup/profile journey now passes in stock Chromium
and Firefox: seventeen setting effects, thirteen painted-popup checks, Custom
70%, framebuffer dimensions and leave/rejoin persistence. This is controls
acceptance, not all graphics/native rendering parity. The native engine-free
root capture also passes genuine Qt pixel and ownership/lifetime checks.

The six current production cohorts are recorded in
[evidence/hub-current-loading-comparison-20261001.json](evidence/hub-current-loading-comparison-20261001.json).
All three Chromium variants pass their four fluid gates. All three Firefox
variants fail fluidness while actual native movement/reconnection succeeds.
Observed model-job readiness upper bounds are20.916/20.457/20.139seconds in
Chromium and21.745/25.529/33.011seconds in Firefox for baseline/shader/texture
respectively. These are live snapshots with three-second observation intervals,
not isolated speed gains. Keep both experiments disabled.

Next: distinguish actual WebEngine command rejection from native focus ownership
loss through fixed scalar metadata in the existing insertion call, then prove a
cause-based correction through the unchanged genuine Create journey in both
stock engines. The additional select-all callback experiment failed Name in
both browsers and was restored exactly; preserve those failures. Actual Firefox
Hub sampled renderer spans now identify approximately16ms draw dispatch and5ms
scene matrices, so prepare measured transform/draw optimizations with exact
graphics/ownership comparisons. Cold decoded-image upload remains a separate
loading priority; owned bitmap preparation requires genuine pixel and lifetime
proof before activation. Preserve the earlier bootstrap failure; its cause
remains unproven. The responsive Create row-group correction
now passes all four real browser cases, including genuine XYZ editing and the
unadapted negative/unchanged desktop controls. Prepare a fresh private audited
native gateway and prove Name/RGB/XYZ/List deletion with all seven baseline
entities preserved. Finish the full source-frozen component/build/browser/repository
reruns, publish reviewed source and run all nineteen isolated Jenkins gates.
Diagnose the actual hosted ancestor-permission failure without relaxing sandbox
rules. Continue supported native Image lighting and remaining complete
Tablet/native features, then actual environment/profile recommendations.

## Ownership and verification

Use all four available slots for useful parallel work: parent integrates and
runs actual services/browser acceptance; transport owns protocol/authority and
native GUI proofs; world owns asset/rendering/loading candidates; laboratory owns
CI, graphics controls and independent review. Restricted agents prepare frozen
TMP proposals; parent reviews complete files and exact before/after hashes before
copying them. Never overwrite concurrent work or infer GPU/native success from VM tests.

Run meaningful protocol/component/browser tests, a production build, actual
native joint journeys and the prescribed repository checks:
`python3 tests/run-project-tests.py --profile quick --timeout 240` and
`git diff --check`. Use the local Jenkins skill and official CLI for its isolated
new job; keep credentials, selectors, profiles, raw logs and PCM private.
Disclose material AI assistance in commits/PR. Keep the existing draft PR current
with truthful exact-commit evidence; publication is a checkpoint, not completion.
