# Passive managed-avatar sampling diagnostics

The integrated default-off adapter adds one explicit operator mode: `OVERTE_LAB_AVATAR_SAMPLE_DIAGNOSTICS=passive` through the managed laboratory, or `OVERTE_GATEWAY_AVATAR_SAMPLE_DIAGNOSTICS=passive` for its gateway. The existing value `1` continues to select full diagnostics. Every other value remains disabled; no browser control enables either mode. Public-place sessions remain excluded from native diagnostic construction and stdout projection regardless of the operator flag.

Passive mode retains timing around the existing position/orientation/rig reads and the existing interstitial signal callback. It does not reread `avatar.position`, call `AvatarList.getAvatarUpdateRate` or access native Stats properties after publication. Those fields are emitted as null using the unchanged fixed numeric/enum stdout schema. It does not retain the native avatar object after completing a sample. The original snapshot, getter sequence, rig-cache policy, avatar send/flush, command application and script intervals are unchanged. Existing current-session/permission/authority checks remain; passive mode is not permission to print revoked data.

Full mode retains the corrected native manager API: `AvatarList.getAvatarUpdateRate(id, '')` and `AvatarList.getAvatarUpdateRate(id, 'globalPosition')`, only after the original publication. This packet is a separate delta over that rate correction. It neither republishes a refreshed position nor forces avatar transmission, Stats refresh, native physics or the loading screen.

All modes retain at most 32 sampled rows, 500 ms diagnostic cadence and 512 emitted rows per helper; signal disconnect and row cleanup remain idempotent. The child projection still enforces its 16 KiB line bound and 512 valid-row quota, rejects private strings/unknown schema fields, and projects only validated fixed JSON. No wire field, browser peer payload, gate, timeout or retry is added.

Validation on the frozen candidate:

```sh
node --test gateway/native-avatar-sample-diagnostics.test.mjs \
  gateway/native-avatar-stdout-projection.test.mjs \
  gateway/native-avatar-passive-integration.test.mjs
```

35 tests passed, zero failed/skipped, 200.077968 ms. Tests run the actual source-extracted `avatarData`, process method, author factory and Python preparation branch. A blocking rig getter proves unchanged old-pose packet/getter order while passive timing reports a 2400 ms publication age. Forbidden native pose/rate/Stats accessors prove zero extra probes. Full and unspecified modes produce identical rows and native calls. Authority replacement suppresses late output, and actual passive rows pass the strict stdout projector. JavaScript syntax and Python AST checks passed. No native/browser/GPU execution or live service change has been performed for this proposal.

The mode remains an observation tool. Clock calls, signal delivery and stdout can still perturb scheduling, so it is lower-interference diagnostic instrumentation rather than proof of zero observer effect. A measured large `publishedPoseAgeMs` can implicate prepublication work; a small value with the old peer pose cannot by itself distinguish stale AvatarList input from an unsent native update. Null probe/rate fields in passive mode mean deliberately unobserved, not zero or missing native capability. Mode and exact source hashes must accompany the report.

## Narrow diagnostic execution recipe

Parent execution only, serial with other native/GPU work:

1. Apply and verify the exact runtime hashes in `manifest.json`; compose only the listed narrow hunks with any parallel server/bridge edits. Build the same product source and attest the original journey sources.
2. Use an already reviewed private network/IPC/PID/mount laboratory owner, or a separately reviewed explicit diagnostic selector on the existing Jenkins namespace runner. Start only that owner's managed lab with `OVERTE_LAB_AVATAR_SAMPLE_DIAGNOSTICS=passive`. A gateway restart alone cannot change a previously running author script; both worker and fixture author must start from the new mode-bound generated scripts.
3. Within that private owner, retain the normal Pulse/Xvfb preparation, signed/pinned host artifacts, unchanged native preflight, operator guest provisioning, explicit absolute slirp path and all-five-zero gate process checks. Run the existing headed core wrapper sequentially, `OVERTE_LAB_BROWSER=chromium bash browser-client/lab/run-core-journey.sh`, then Firefox with its corresponding existing browser setting. Keep `OVERTE_LAB_DURATION_SECONDS=0`, the original 2800 ms peer assertion, native scene/voice/input/rejoin gates and ordinary captured snapshot assertion. This is a focused diagnostic core pair, not all nineteen CI stages.
4. Always stop only the owner's registry-verified services and collect the ordinary curated core evidence plus private validated `BROWSER_AVATAR_SAMPLE` rows. Record fixture freshness: a later repeated target is not a new successful movement observation.

The current Jenkins `run.py` refuses dirty/uncommitted helpers for full CI and has only a namespace-only `--probe-only` selector. Do not repurpose that flag to start native services, bypass source checks, modify an existing Jenkins job, or claim a focused pair as a nineteen-gate pass. This packet intentionally does not weaken or fork those safeguards. Until an explicit reviewed focused selector is available, the recipe requires the parent's already owned, isolated managed-lab execution context.

Parent integration reran the35 diagnostic contracts and six trusted fixed-phase
collector contracts: all41 passed (175.369049ms). All1,417 registered
components also passed, with zero skips (11.522537s), and the current
production build passed. Actual passive-mode native qualification remains
required; these CPU checks do not resolve the failed original movement gate.
