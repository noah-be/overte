# Private native worker refresh initialization

This experiment is **OFF by default** and requires explicit
`OVERTE_GATEWAY_NATIVE_REFRESH_QOS=1`. It changes newly created dedicated gateway profiles, not visitor
WebGL settings, pixel ratio, quality, scripts' protocol timers or existing
native processes. Actual native readback, CPU delta, Tablet capture/input,
voice, avatar/pose and reconnect proofs remain required before activation.
This is initialization QoS, not a security-enforced CPU quota: visitor scripts
can subsequently modify their own native worker settings.

The narrow patch applies only to the private `Interface.json` payload in
Session.launch. Apply it against the recorded server hash, not the snapshot's
complete server. It preserves the existing private input/output, desktop mute,
first-run flag and worker viewport scale0.1. The added fixed values are:

| Setting | Value |
| --- | --- |
| `performancePreset` | CUSTOM5 |
| `refreshRateProfile` | CUSTOM3 |
| `customRefreshRateFocusActive` | 10Hz |
| `customRefreshRateFocusInactive` | 10Hz |
| `customRefreshRateUnfocus` | 10Hz |
| `customRefreshRateMinimized` | 2Hz |
| `customRefreshRateStartup` | 10Hz |
| `customRefreshRateShutdown` | 30Hz |

These are native source-defined setting/enum values. No untrusted browser field
or new configurable unbounded target is introduced. RefreshRateManager reads
its profile/custom settings at construction. PerformanceManager's CUSTOM5
performs no preset application and, with firstRun false, avoids platform
auto-selection overwriting refreshRateProfile with REALTIME/ECO. Skipping that
automatic worker preset selection also means remaining native worker render
defaults must be observed; this proposal does not claim all worker graphics
configuration is byte-for-byte equivalent to the prior automatically selected
preset. Visitor graphics remain separate and unchanged.

Reviewed primary native files:

- `interface/src/RefreshRateManager.h`: complete profile/regime enum and setting keys.
- `interface/src/RefreshRateManager.cpp`: constructor reads, custom target lookup, update controller.
- `interface/src/PerformanceManager.h`: CUSTOM performance preset5.
- `interface/src/PerformanceManager.cpp`: automatic UNKNOWN platform selection and CUSTOM no-op.
- `interface/src/Application.cpp`: loadSettings calls setupPerformancePresetSettings.
- `interface/src/scripting/PerformanceScriptingInterface.h/.cpp`: readback methods and profile script enum.
- `libraries/script-engine/src/ScriptEngineCast.h`: script setters reject enum values not registered in their meta-enum.
- `libraries/display-plugins/src/display-plugins/OpenGLDisplayPlugin.cpp`: present-thread refresh operator and sleep.
- `libraries/display-plugins/src/display-plugins/RefreshRateController.cpp`: bounded native present-thread sleep.
- `interface/src/Application_Events.cpp`: onPresent schedules idle/render events.

In particular, CUSTOM3 is absent from PerformanceScriptingInterface's profile
enum even though RefreshRateManager supports it. Calling numeric3 through that
script setter is rejected; this patch uses the genuine private constructor
settings path. The public script ECO profile alone is a separate valid option,
but it targets20Hz focused-active/10inactive/5unfocused, not a uniform10Hz worker.

Readback source is optional and read-only. Append
`native-worker-refresh-readback.js` and `native-worker-refresh-probe.js` to the
trusted script of a freshly created owned diagnostic worker, retaining its
normal bridge/default scripts. The six one-second aggregate log records contain
only numeric preset/profile/regime/target/custom values and timestamp; no
device labels, URLs, participant identity, credentials or operator paths.
`applied` requires exact custom rates, CUSTOM preset/profile and the effective
selected target matching the current regime. `targetHz` is the requested native
refresh target, not a measured rendered FPS. Missing APIs or a reset must stay
explicitly unavailable/non-applied. CPU deltas and actual render cadence need
independent measurements. Script teardown clears the diagnostic interval.

The existing owned local laboratory observer does not receive these settings
from this gateway patch. To measure reduced local observer overhead, the parent
must create a separate legitimate fresh private profile with the same values
and restart only that explicitly owned observer. Other native/user processes
are preserved. Existing live workers likewise remain untouched.

CPU validation:

```sh
node gateway/native-worker-refresh.test.mjs
```

Six tests evaluate the actual production private settings object, verify six
native readback regimes, preserve source-reset/profile/target mismatches and
refuse missing/invalid APIs without calling native setters. They establish
source contracts only, including bounded diagnostic cleanup. The pinned f91 native runtime and real browser/private
domain journeys must supply the remaining evidence.

## Actual short Tablet outcomes

With the CUSTOM refresh experiment enabled, the first ten native Graphics
control changes passed but reconnect failed. Two subsequent short cohorts
received no native Tablet frame within the unchanged30second deadline. The
experiment was disabled rather than weakening that acceptance bound. Normal
private initialization then passed both Chromium and stock Firefox Graphics
control/rejoin journeys. This is not an isolated cadence comparison: CUSTOM5
also skips automatic native Render/LOD preset initialization. The optional
`OVERTE_GATEWAY_REFRESH_DIAGNOSTICS=1` probe only reads six bounded records.
Standalone native readback is a separate diagnostic and does not establish
actual sandboxed-worker Tablet, voice or pose regression acceptance.
