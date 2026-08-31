# iOS development status

The detailed implementation inventory remains in
[`docs/ios/PORT_STATUS.md`](../../ios/PORT_STATUS.md). This page summarizes the
boundary a new developer must understand.

## Validated bootstrap

- native UIKit and Metal application;
- iPhone and iPad simulator launch;
- unsigned arm64 device-SDK compilation and packaging;
- lifecycle, deep-link, place-resolution, bundle, privacy, and architecture
  contracts; and
- machine-readable physical-device acceptance definitions.

## Experimental integrated client

- Qt 6.11.1 and Conan graph boundaries exist;
- desktop-only modules and unsupported dynamic plug-ins fail closed; and
- V8, MoltenVK, rendering, Qt Multimedia, and dependency recipes still have open
  integration work.

## External gates

Physical-device rendering, audio, microphone, touch, thermal, memory, signing,
and privacy aggregation require explicitly authorized iPhone and iPad access.
App Store submission is outside the current developer-artifact milestone.

## Touch acceptance paired with the next rendering build

At the device tester's explicit request, the physical rendering build contains
the shared fixes integrated through `main` from the former
`fix/universal-touch-ui-tablet-qml` branch rather than duplicating them as an
`apple-ios` implementation:

- tablet startup and direct touch interaction: `55da2d017e`, `2361d3a9b5`;
- shared TextField context fix: `54d6103edc`.

Validate on both iPhone and iPad that tablet icons appear, short taps work,
swipes do not trigger icons, and Goto/Login/other text fields open the iOS
system keyboard on a short tap. Also validate focus, keyboard geometry, safe
areas, and resize behavior.

## Physical-device iteration controls

The iOS client enables the expanded statistics overlay by default so render
rate, present rate, position, network and scene counters are visible during
device acceptance. Unlike the reduced Android FPS badge, the iOS selector uses
an iPad-sized three-column diagnostic panel.

`Documents/overte-ios-render-diagnostics.json` selects Web/QML upload
diagnostics without rebuilding. Supported fields are:

```json
{
  "mode": "normal",
  "format": "rgba",
  "flipVertical": true,
  "forceOpaque": false,
  "captureFirstFrame": true,
  "captureFrameOrdinals": [1, 2, 4, 8],
  "captureLatestFrameSequence": 1,
  "captureSourceContains": "Wizard.qml",
  "screenQmlFlipVertical": true,
  "screenQmlCaptureFrameOrdinals": [1, 4, 8],
  "screenQmlCaptureLatestFrameSequence": 1,
  "qmlSoftwareWarmupFrames": 8,
  "qmlSoftwareDiagnosticContinuousFps": 0,
  "statsOverlay": true,
  "statsOverlayExpanded": true,
  "touchUiAutoOpenTablet": false,
  "virtualPadForceVisible": true,
  "virtualPadScalePercent": 100,
  "touchJumpMinimumPulseMs": 120,
  "touchInputTraceLimit": 64,
  "offscreenKeyTraceLimit": 64,
  "locomotionTraceIntervalMs": 250,
  "cameraMode": "third-person"
}
```

`mode` is `normal` or `test-pattern`. `format` is `rgba`, `srgb`, `bgra`, or
`rgba-from-bgra`. The first-frame log includes visible/opaque/non-black pixel
counts and corner/center RGBA samples. When capture is enabled, the exact image
sent to Vulkan is written to `Documents/Overte-iOS-QML-FirstFrame-*.png` for
AFC retrieval. Later ordinals use `Overte-iOS-QML-Frame-*.png`. Increment
`captureLatestFrameSequence` to request another current frame. Set
`qmlSoftwareDiagnosticContinuousFps` from 1 through 15 when otherwise static
QML must keep producing frames for a live investigation, then return it to 0.
The JSON is checked for updates once per second; these controls do not require
an app restart.

Screen-space QML (statistics, mobile action bar, dialogs, and tablet) has its
own `OVERTE_IOS_SCREEN_QML_FRAME_GATE` marker and capture ordinals. The iOS
Vulkan HUD also draws the virtual movement pad and jump/handshake buttons;
`virtualPadForceVisible` provides a visual diagnostic fallback before scripts
finish, while `virtualPadScalePercent` accepts 50 through 200. `cameraMode` is
`third-person` (the iOS default), `first-person`, or `persisted`.
`touchInputTraceLimit` bounds classification markers for move, view and button
touches; set it to 0 after input acceptance. `touchJumpMinimumPulseMs` keeps a
short jump tap visible to at least one mapper update even when the first iOS
frame after release exceeds the configured pulse; `stage=jump-pulse-exposed`
records that guaranteed sample. `offscreenKeyTraceLimit`
bounds hardware-keyboard routing markers without logging typed text, and
`locomotionTraceIntervalMs` controls the active locomotion-state marker cadence.
Set either trace value to 0 to disable its corresponding diagnostic.

Set `touchUiAutoOpenTablet` for a launch that must expose the screen-space
tablet without a manual tap. This exercises the same shared tablet presenter as
the selected phone scripts, but uses live UIKit safe-area, surface, density and
keyboard metrics from the existing `+ios/TouchUiProfile.qml` adapter. The
`OVERTE_IOS_TOUCH_UI_GATE` markers report metrics, resize bounds, registered
buttons and final visibility. `statsOverlay` and `statsOverlayExpanded` permit
clean comparison screenshots without another IPA.

On iOS, the offscreen HUD, tablet window and incoming Qt touch positions all use
the same safe-content-local coordinate space. UIKit safe-area insets are removed
exactly once when the render target is sized; controls and QML windows must not
subtract the top or bottom inset a second time. Hardware-keyboard events are
routed to the active offscreen QML focus item, while the native input assistant
is suppressed without disabling text input.

Reviewed QML can also be replaced without rebuilding. Create
`Documents/OverteQmlOverrides/.enabled` and mirror the QRC-relative file path
below that directory, for example
`Documents/OverteQmlOverrides/serverless/Scripts/Wizard.qml`. Only regular,
non-symlink files canonically contained by that root are accepted, and every
active override is recorded by `OVERTE_IOS_QML_OVERRIDE_GATE`. If an override
uses relative imports, mirror those dependencies as well. Remove `.enabled` to
return atomically to bundled QML.

There is a separate orientation-product conflict to resolve first: Android
acceptance requires the touch app to start and remain landscape regardless of
Auto-Rotate, while the current iOS matrix still requires portrait/landscape
rotation, Split View, and Stage Manager. Decide the desired orientation for
iPhone and iPad separately before implementing or testing an iOS orientation
lock. Shared Touch UI contract changes originate from main; only any remaining
native iOS focus, keyboard, or orientation adaptation originates from
`apple-ios`.
