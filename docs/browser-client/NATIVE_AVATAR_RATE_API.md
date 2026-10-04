# Managed avatar update-rate diagnostic API

This source-only follow-up corrects the opt-in laboratory diagnostic. It changes no avatar packet, original pose/rig sampling, publication order, permission gate, timer or deadline.

Pinned native source: `f91d15a08587dcd37c642234424b3215dd331724`.

- `interface/src/Application.cpp:563` registers the actual `AvatarManager` as `AvatarList`.
- `interface/src/avatar/AvatarManager.h:114` returns a new `ScriptAvatar` from `getAvatar`. `ScriptAvatar` inherits `ScriptAvatarData`, whose superclass is QObject. Neither wrapper exposes `getUpdateRate`.
- `AvatarManager.h:157` exposes `getAvatarUpdateRate(sessionID, rateName)` as Q_INVOKABLE. Its implementation at `AvatarManager.cpp:212–214` looks up the existing avatar and delegates to `AvatarData::getUpdateRate`. It performs no send or forced refresh.
- `libraries/avatars/src/AvatarData.cpp:1650–1654` defines the exact keys `""` for parsed packet rate and `"globalPosition"` for global-position field update rate.

The existing original peer fields were null because the unavailable wrapper method was checked before invocation. They remain unknown evidence, not measurements of paused transmission.

The corrected diagnostic uses the already-published result UUID, avoiding an extra native identity read. It invokes the existing manager API only for the exact fixture peer, only after the original send/flush, under the existing captured approval and publication sampling bounds. Invalid/nil UUIDs, missing API and native exceptions remain null. A native zero is retained as zero; the native API also returns zero for an absent avatar, so zero alone cannot establish paused transmission or a surviving peer. No UUID is added to diagnostic output.

Validation: `node --test gateway/native-avatar-sample-diagnostics.test.mjs` in the candidate browser-client directory: 16 passed, no skips. Actual-production functions run in a VM with a wrapper lacking the nonexistent method. The explicit original-function negative control reproduces both null fields despite an available manager API. Other cases verify exact UUID/keys, post-publication ordering, disappearing-peer semantics, revocation between reads, unchanged original output and native getter order, private error refusal and bounded sampling.

No native/browser/GPU workload was run for this follow-up. It establishes an API correction, not a throughput, startup, latency or historical CI cause.
