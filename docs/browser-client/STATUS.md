# Browser client status

Last updated: 2026-09-30. **Implementation and real functional verification passed; production delivery prepared for review.**

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
- `build/repository-checks-env/bin/python tests/run-project-tests.py --profile quick --timeout 240 --junit build/test-results/browser-client-delivery-project-tests.xml`:
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
The production UI is running and opened at `http://127.0.0.1:8090`.

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
