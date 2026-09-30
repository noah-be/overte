# Browser client implementation plan

This is an explicitly authorized session project, independent of the product roadmap.
Base: fork `main`, `e6ba29f4819fefdc3b212fd00abcf9dbbb6b4999`.
Topic: `feature/main/browser-client`. Material implementation assistance: OpenAI Codex.

## Required outcome

A self-hostable browser-rendered Overte client with real domain entities/assets,
movement and collisions, visible native/browser avatars, bidirectional native
voice, interaction, reconnect, production distribution, Chromium and Firefox
verification and short real shared native/browser functional tests.
The user explicitly cancelled the 30-minute endurance requirement during this
session on 2026-09-30. Do not run an endurance test or treat its absence as a blocker.
All other functional requirements remain mandatory when an implementation stage fails.

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
Only after every required outcome passes, commit, verify the fork push URL,
push the topic and open/read back an English draft PR with AI disclosure.
