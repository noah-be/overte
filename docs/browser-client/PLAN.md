# Browser client implementation plan

This is an explicitly authorized session project, independent of the product roadmap.
Base: fork `main`, `e6ba29f4819fefdc3b212fd00abcf9dbbb6b4999`.
During delivery, integrated the newer fork `main` commit
`d569930678d2edb61330a96bcdcab17ee68a732f` after exact CI identity checks
exposed a stale GitHub base snapshot. Browser runtime remains unchanged.
Topic: `feature/main/browser-client`. Material implementation assistance: OpenAI Codex.

## Required outcome

A self-hostable browser-rendered Overte client with real domain entities/assets,
movement and collisions, visible native/browser avatars, bidirectional native
voice, interaction, reconnect, production distribution, Chromium and Firefox
verification and short real shared native/browser functional tests.
The user explicitly cancelled the 30-minute endurance requirement during this
session on 2026-09-30. Do not run an endurance test or treat its absence as a blocker.
All other functional requirements remain mandatory when an implementation stage fails.
On 2026-10-01 the user made world and texture loading immediately after admission
an explicit immediate priority. Measure the cold real-Hub loading phases, then
integrate and measure cache/scheduling, early genuine collision geometry and
audited compressed-color assets in separate source-frozen cohorts. Do not wait
for the later optional ordering of systematic optimization to fix current loading.
On 2026-09-30 the user explicitly added mandatory goals: a fully functional
browser Tablet, access to online worlds and fluid movement, verified in the
actual public `overte_hub`. These supersede the earlier Tablet deferral. The
original functional baseline remains required. Public-world testing must be
muted/read-only and preserve normal user admission and permissions.

## Architecture investigation

Historical `WEBRTC_DATA_CHANNELS` is disabled on the supported native platforms.
Audio processing libraries do not provide browser networking. Reviewed
[Vircadia Web SDK](https://github.com/vircadia/vircadia-web-sdk) and
[Vircadia Web](https://github.com/vircadia/vircadia-web): they require corresponding
native WebRTC data channels and compatible protocol versions, so direct reuse is
not assumed. Selected renderer: Three.js with actual native entity JSON and model
loaders. Selected transport: an isolated native-protocol session per browser,
behind a self-hostable gateway. It preserves normal anonymous domain permissions
and refuses authenticated/source-IP/fingerprint policies. Operator-managed
settings and effective native rights must agree before releasing session data.
No claim of arbitrary public domain compatibility.

## Stages and ownership

1. Connection: transport agent owns native gateway/protocol; laboratory agent
   owns isolated domain and native builds. Parent integrates browser session UI.
2. Real world/assets: world agent owns renderer, mapping and asset resolution.
3. Movement/avatars: world agent owns controls/collisions/visuals; transport
   agent owns native state synchronization.
4. Audio/interaction: parent owns browser microphone/playback; transport agent
   owns native audio and permission-preserving entity operations.
5. Stability/distribution: parent owns integration, self-hosting guide, CI,
   required repository checks and review; laboratory agent owns real journey
   evidence and short functional testing.

Keep interfaces explicit, test failures meaningful, session credentials private,
and existing worktrees/services unchanged. Never infer success from mocks.

## Exit evidence

Record exact versions and commands, real domain and native coexistence results,
browser rendering and workflow tests, both voice directions (distinguishing
synthetic input from a physical microphone), interaction, reconnect and duration.
Publish tested, explicitly scoped checkpoints on the authorized topic and
existing English draft PR with AI disclosure. Verify the actual fork push URL
before each push. Keep the goal active and report completion only after every
required outcome passes; publication does not waive unfinished requirements.

## Additional required stage: Tablet and online worlds

- Transport agent: actual public guest/domain lookup, authentication/permissions
  preservation, public asset origins and safe gateway session integration.
- World agent: actual native Tablet/application reuse or complete browser Tablet
  implementation; coordinate native/gateway integration instead of placeholder UI.
- Laboratory agent: isolated, muted native/public-Hub connection, actual scene
  and permission evidence, Tablet fixtures and measured browser performance.
- Parent: visitor-device rendering performance, browser UI integration, complete
  Tablet/online journeys, production distribution and unchanged CI gates.

Next: establish an actual `overte_hub` guest connection and native Tablet API/app
requirements. Select the architecture from working tests, then implement and
verify real Tablet actions and smooth online navigation in Chromium and Firefox.
The active Codex goal remains open; earlier baseline delivery is not completion
of the expanded requirement. No 30-minute test is authorized.

## User-authorized continuation after initial and added goals

On 2026-09-30 the user explicitly requested autonomous continuation after all
previous goals pass: implement and test the features provided by the other
Overte clients. Full desktop/Tablet/world-building/VR feature parity is therefore
a subsequent mandatory stage, rather than a permanently excluded scope.
Complete the original baseline, functional Tablet and actual online-Hub journey
first; then maintain a source-derived feature inventory and implement/test its
remaining entries. Preserve authentication, device boundaries and actual proof.
Do not mark absent hardware or untested integrations as passing.

Next after the initial/Tablet/Hub acceptance: inventory native client menus,
applications, scripting/rendering/avatar/audio/networking and device features;
map each to browser implementation and reproducible acceptance evidence. Continue
autonomously through this inventory without another authorization request.

## Subsequent graphics and stability goals

The user additionally instructed on 2026-09-30: after all preceding requirements
are complete, implement useful browser graphics profiles, selectable through the
Tablet. Expose every implemented graphics option that actually works in the
browser renderer, including a render-resolution control expressed as a percentage.
Native settings that have no browser effect must not appear to succeed.

After those controls are complete, implement an automatic browser-environment
scan and recommend appropriate graphics settings from its actual capabilities
and measured performance. Explain the recommendation and let the visitor apply
it; do not silently claim a fixed hardware guess is optimal.

Finally, after the previous goals pass, run actual browser stability tests in
`overte_hub`, investigate measured stalls/errors/crashes and fix their causes
autonomously. The explicitly cancelled 30-minute/endurance requirement remains
cancelled; the added stability work does not restore an arbitrary session length.
Keep these stages and their acceptance evidence in the active goal and status.

After those additional goals pass, the user also requires a further autonomous
optimization stage, particularly texture/asset loading and visitor-device
rendering. Profile actual bottlenecks, implement bounded caching/scheduling or
rendering improvements where supported, and compare reproducible load/frame-time
measurements while retaining visual correctness, permissions and all existing
acceptance checks. Necessary performance fixes for the current mandatory Hub
journey continue immediately; this later stage adds systematic optimization.


## Execution platform continuation (2026-10-01)

The isolated topic worktree and Git metadata became read-only during active
implementation. Local network listeners and browser IPC now return EPERM;
escalation is unavailable. Preserve the topic and existing protections. Continue
independent source work and offline verification only in the writable temporary
snapshot described in STATUS.md. Record exact base hashes before offering an
integration patch; refuse overwriting concurrent user/agent changes. A build or
mocked scheduler test does not satisfy actual native/browser acceptance. The
active goal remains unfinished, including all added parity, graphics, stability
and optimization stages. Do not reinstate the cancelled endurance requirement.

## Restored CLI permissions (2026-10-01)

The user enabled Full access. Exact before/after SHA checks protected the existing
topic files while integrating the 35-file continuation. The full-checkout build
and ordinary 314-test component suite pass. The owned gateway was restarted after
process identity checks; genuine browser/native acceptance and remaining stages
continue on the authorized topic. The earlier restricted-platform section is
historical, not the current access state. No cancelled endurance test is restored.

## Immediate loading priority (2026-10-01 user steering)

The user explicitly requires faster world and texture loading immediately after
joining. This optimization now runs alongside current acceptance rather than
waiting for complete future feature parity. The actual muted Hub baseline is
42.125 seconds from admission to all model tasks finished, with 1,303 asset
requests/664 unique URLs/639 duplicate requests. Transport owns per-session
authority-bound bytes/in-flight deduplication; world owns per-world shared image
sources and bounded independent map loads; lab owns off-main-thread bounded FBX
preparation. Preserve geometry/material semantics, cancellation/resource limits
and admission on every cache read. Compare actual load/frame metrics and visuals
before claiming an improvement. All earlier requirements remain active.

## Loading checkpoint and next concrete integration (2026-10-01)

Bounded embedded-image reuse is now integrated and genuinelyGPU/native tested.
The strictHub cohort establishes fewer decode/upload identities, not a causal
whole-world speed guarantee. Firefoxfluidity remains failed. Exact-zero-light
shader optimization was actually tried and returned to defaultoff after no
demonstrated benefit. Next integrate bounded GPU/CPU frame observation, use its
actual measurements to select the next rendering change, and implement genuine
Create edit/delete plus browser-effective native Tablet Graphics controls.
HostedUbuntu corrections preserve all sandbox and acceptance gates.
