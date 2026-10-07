# Browser graphics inventory and current-screen fullscreen proposal

This is a source review and an unintegrated TMP proposal. No browser, native Interface, GPU, server or system process was launched. CPU fixtures do not establish actual fullscreen support or native Interface key routing.

## Effective controls and accepted evidence

| Browser Tablet option | Actual effect | Evidence and limits |
| --- | --- | --- |
| Field of view,20–130° | Changes the visitor PerspectiveCamera vertical projection | Genuine native Settings slider/ACK in both stock engines; separate BrowserWorld projection fixture |
| Resolution,10–200%,10% steps | Sets drawing density relative to the initial `min(devicePixelRatio,2)` | Hardware dimensions are checked before mutation. Actual native 100/80/60/Custom70%, framebuffer dimensions and leave/rejoin persistence qualified in both stock engines. This is not a cap of2 after an explicit percentage increase. |
| Local lights | Changes actual visitor point/spot contributions | Genuine native switch/ACK plus separate real BrowserWorld light pixels, including off/relit |
| Allow camera clipping | Inverse of visitor third-person collision-constrained camera | Genuine native switch/ACK plus separate actual constrained/free/restored camera fixture |
| Default/Balanced/Faster/Custom | Resolution-only100/80/60/current custom percentage | Actual painted native popup selection;17 effects and13 popup checks per stock engine. These are not native Low Power/Low/Medium/High render presets or a measured automatic recommendation. |

The current read-only `__overte.graphics` reports the four effective settings. The schema has no other graphics controls. Persisted settings are restored to the new visitor World; stale permission revisions and replayed request IDs cannot change or save them. A rejected allocation leaves prior camera/density/switches unchanged.

The native-source comparison is exactly `f91d15a08587dcd37c642234424b3215dd331724:scripts/system/settings/qml/pages/GraphicsSettings.qml`,SHA256 `f1eda115ef4504e355002dc5a2a238385374cd09f2247e187e5aa0392b75b313`. It additionally has Bloom,Custom Shaders,Deferred Rendering,Shadows,Ambient Occlusion,Haze,anti-aliasing(None/TAA/FXAA or forward MSAA),LOD,refresh profiles and six custom refresh states,fullscreen display selection,and native quality presets. These are absent from the browser settings. The browser uses a fixed forward Three renderer,requested antialiasing,ACES tone mapping andSRGB output; requesting antialiasing is not proof that an option or a specific MSAA count works. Unintegrated Zone/presentation prototypes are not effective settings.

The adapter already tells users that additional graphics options are unavailable. The automatic browser-environment scan and explained recommendations remain unimplemented,as recorded in FEATURE_PARITY.md. No proposed scanner or preset should infer a physical GPU from a privacy-sanitized Firefox renderer string or reduce density automatically.

Accepted controls evidence is GRAPHICS_OWN_ROOT_VERIFICATION.md and its two source-coherent20261001 stock reports. The older tablet-graphics-runtime-20261001.json retains both positive and negative experiments; it is not the later17/13 qualification. Current Hub fluidness results supplied by the parent pass all four default-quality gates in both stock engines; historical Firefox failures are not a current failure claim.

## One bounded missing feature

The new Fullscreen/Exit fullscreen button is in the **browser-owned visible Tablet toolbar**,outside the native capture canvas. It calls the real browser API directly in its trusted click stack. It fullscreens the existing application container,so closing the Tablet can reveal the same World presentation. It sends no native command and does not change the renderer,percentage,quality,permissions or native Settings schema.

This is current-screen browser fullscreen,not the native Fullscreen Display menu or monitor selection. The WHATWG [Fullscreen API](https://fullscreen.spec.whatwg.org/) defines requestFullscreen's transient-activation requirement,the actual fullscreenElement readback and fullscreenchange event. A native QML→WebSocket→browser roundtrip cannot guarantee retained activation,so that route is not used. No keyboard lock or Window Management permission is requested.

The button shows actual fullscreen state,tracks external Escape/change events,disables while a platform request is pending,and provides a separate wrapping status message for unsupported/denied operation. Native canvas input continues using actual getBoundingClientRect and the existing frame ownership. Closing only the Tablet does not exit fullscreen. Disconnect/dispose promptly cancels the owned wait and releases established owned fullscreen. Rejoin starts from actual platform state. A per-target weak lease prevents obsolete controllers from exiting a replacement controller's presentation. Foreign fullscreen elements are never exited.

One outstanding browser operation per target is allowed. Our confirmation wait is bounded8s; the browser API itself cannot be cancelled. A never-settling platform promise keeps the button pending and gives an explicit reload message. Late success cannot retroactively acknowledge a timed-out request; late rejection is consumed. No per-frame work,asset request,renderer invocation,screen enumeration or persistent setting is introduced.

## Qualification

-11 CPU contracts pass with real promise/task boundaries and controlled API boundary fakes. They cover same-click synchronous invocation,truthful readback,unsupported/detached/disconnected/synthetic refusal,foreign view,denial,duplicate operations,Escape readback,prompt cancellation,late completion/replacement,timeout,late rejection,idempotence and callback-driven cancellation.
- Whole current project plus new TMP files typecheck passes. Initial TMP typecheck failures were missing borrowed shared modules and an ES2023-only fixture method; these were corrected in the proposal and are not production failures.
- Three registered browser cases are **prepared,not executed**: real trusted enter/exit/Escape plus leave/rejoin and disposal;360×560 navigation/canvas aspect;actual Permissions Policy refusal without losing canvas input. No production feature or actual browser acceptance is claimed.

After applying the patch and new files in a reviewed temporary tree,use ordinary test discovery for `tests/fullscreen.test.ts` and `tests/tablet-fullscreen.browser.spec.ts`. The parent must run the unchanged registered bodies in stock Chromium154 and Firefox156,with genuine clicks and normal browser security,verify actual application fullscreen/escape and responsive layout,and then repeat a real native Tablet journey to confirm existing painted controls and input calibration remain unchanged. No native image oracle is replaced by an authored canvas proof.

Only src/tablet.ts is patched. No World/main/native graphics/Sit/PTT source changes are included. Do not copy borrowed symlinked source folders from the working candidate;integrate only the manifest files and patch.
