# Mobile world appearance controls

Android Phone exposes native Graphics settings for local lights, haze, custom
material shaders and mirrors. It also allows render resolution from 50% to 70%
while retaining the existing 30 FPS target. Choices persist across restarts.
The Android product profile enables this page only after the shared controller
and Settings message routing have been integrated.

The startup list is shared with iOS. The controller therefore requires both the
immutable Phone startup flag and the native platform's Android OS identity
before touching renderer state. Only the first-party Settings screen can submit
changes. Other applications, malformed keys and values outside the supported
budget have no effect. Enabling lights restores the full clustering grid before
admitting light content; disabling them stops lights before reducing the grid.

`GraphicsSettingsBase.qml` retains the generic Graphics page. The unselected
`GraphicsSettings.qml` remains a compatibility entry, and iOS must select a thin
`+ios/GraphicsSettings.qml` wrapper around the generic body when the shared
Phone selector is propagated. This preserves the existing iOS page.

Run the shared behavior checks from the repository root:

```bash
node --test tests/javascript/test/phone-graphics.production.test.js
node --test tests/javascript/test/default-scripts.production.test.js
python3 tests/device/contracts/tablet/test_tablet_qml.py
python3 tests/run-project-tests.py --profile quick --timeout 240
git diff --check
```

The Phone branch additionally owns real Qt 5 pointer, narrow-layout and font
scale tests. Host checks establish message routing and UI behavior; physical
acceptance still requires each effect to be visible in the common reference
world, restart persistence and performance observations on the exact APK.
