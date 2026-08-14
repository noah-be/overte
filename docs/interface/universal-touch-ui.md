# Universal touch UI

Overte's touch UI should adapt to the capabilities and usable geometry of a
surface, not to a list of device model names. A device integration supplies a
small capability profile; shared QML derives layout measurements from it.

## Layers

1. `controlsUit/TouchUiProfileBase.qml` defines platform-neutral defaults for
   input, host presentation and available features.
2. A device selector overrides only the capabilities that differ. Android
   Phone does this once in `controlsUit/+android_phoneInterface/TouchUiProfile.qml`.
3. The platform host consumes safe-area and content-scale values, while
   `controlsUit/TouchUiMetrics.qml` converts usable feature geometry into width
   classes, target sizes and spacing.
4. Feature-level presentation objects map those shared capabilities to a
   feature. `TabletTouchConfigurationBase.qml` and the Audio, Avatar, Security,
   Settings and General Preferences policies use this layer.
5. Feature screens consume only their presentation object and keep their
   behavior and scripting APIs platform-independent.

This preserves the existing `Tablet` scripting API. It also lets pointer-only
desktop and VR tablet surfaces retain their current measurements while direct
touch surfaces opt into the accessible touch baseline.

## Device adapter contract

A device adapter may set these profile inputs:

- `directTouch`
- `hoverSupported`
- `hapticsSupported`
- `hardwareKeyboardSupported`
- `systemImeAvailable`, `keyboardVisible`, and `imeInsetBottom`
- `screenSpacePresentation` and `screenSpaceContentScale`
- `safeInsetLeft`, `safeInsetTop`, `safeInsetRight`, and `safeInsetBottom`
- `surfaceWidth`, `surfaceHeight`, `density`, and `fontScale`
- feature capabilities such as `graphicsSettingsAvailable` or
  `scriptingPluginsAvailable`

Each feature supplies its current `availableWidth` and `availableHeight` to its
presentation object. A host that has not already removed its safe area may
also supply the four inset values directly to `TouchUiMetrics`.

Adapters must not copy a feature screen or redefine feature layout values. A
new touch device starts with one profile selector; device-specific QML should
be added elsewhere only when a hardware or operating-system constraint cannot
be represented by the shared inputs.

The Android phone selector is the reference adapter. It declares direct touch
and screen-space presentation, then consumes live host measurements for input
capabilities and geometry. Its launcher columns and measurements come from the
shared base. Conservative startup values apply only until the first valid
native snapshot arrives.

Runtime measurements are trusted only after both Java and native validation.
An adapter must reject invalid surfaces, clamp hostile insets and non-finite
scales, preserve asymmetric cutouts, and leave at least one usable pixel on
each axis. Feature QML reads the resulting map but cannot replace it through
the scripting API.

## Responsive contract

The initial width classes use logical QML pixels:

- compact: less than 600 usable pixels
- medium: 600 through 839 usable pixels
- expanded: 840 usable pixels or more

Usable size excludes safe-area insets. Direct-touch controls use a minimum
rendered target of 48 pixels. `Button`, `Slider`, `Switch`, `CheckBox`,
`TextField`, menu, radio, combo, spin and scroll controls convert that target
into local coordinates when a screen-space host scales the complete QML
surface. Feature layouts may be denser on pointer-only surfaces, but they must
not infer input capabilities from width alone.

System font scale is bounded to 1.0 through 1.5 in feature layout. Controls may
grow to avoid clipping, and compact action groups must reflow instead of
shrinking below their rendered touch target. Direct-touch scrolling uses one
press delay and one bounded flick policy so that a drag does not accidentally
activate a row. Hybrid mouse/stylus devices retain hover without changing the
direct-touch target size.

## Android runtime pipeline

`PhoneInterfaceActivity` observes the decor surface, `WindowInsets`,
configuration and input-device changes. On Android 11 and newer it reads
system bars, display cutouts, mandatory system gestures and the IME separately;
older releases use a tested policy that separates the transient keyboard from
stable navigation protection. This follows Android's
[edge-to-edge guidance](https://developer.android.com/develop/ui/views/layout/edge-to-edge)
and the [`WindowInsets` contract](https://developer.android.com/reference/android/view/WindowInsets.html).

The snapshot crosses JNI asynchronously, is validated again by
`PhoneTouchUiMetrics.h`, and is published as the read-only
`Tablet.touchUiRuntimeMetrics` property. The selected Phone profile consumes
that property. `TabletScriptingInterface` resizes an open screen-space tablet
to the current surface minus asymmetric safe and IME insets; the mobile action
bar applies the same measurements in Qt window coordinates. Rotation,
multi-window resizing, keyboard visibility and input-device changes therefore
update the open UI without rebuilding feature screens.

Phone text entry uses the Android system IME. The legacy QML keyboard remains
available to HMD/offscreen hosts only. Forms provide content-specific input
hints, scroll the focused field into view when the IME appears and hide the
keyboard during teardown. `adjustResize` remains enabled as recommended by
Android's [keyboard visibility guidance](https://developer.android.com/develop/ui/views/touch-and-input/keyboard-input/visibility),
while explicit IME insets cover enforced edge-to-edge layouts.

## Adoption order

Adopt the foundation one complete user path at a time:

1. system tablet launcher and navigation
2. dialogs, text input and software-keyboard behavior
3. settings controls and preferences
4. avatar, audio and security screens
5. the mobile action bar and remaining platform-specific screens

The launcher/navigation, address and login forms, system-IME web surfaces,
settings/preferences, avatar, audio, security, Emote, tablet menu and mobile
action-bar paths now follow this contract. For each additional path, move
shared measurements into a feature presentation object, leave only
capabilities in the single device profile, and add compact, medium, expanded,
font-scale and pointer-compatibility tests before removing duplicated platform
QML.

## Adding another touch device

1. Add one selector-backed `TouchUiProfile.qml` adapter for the platform.
2. Feed validated surface, safe-area, scale, IME and input capabilities into
   that adapter. Reuse `Tablet.touchUiRuntimeMetrics` only when the host owns an
   equally trusted native measurement boundary.
3. Keep feature flags in the adapter and layout policy in shared metrics or a
   feature configuration. Do not add device-model checks to feature QML.
4. Run the host device matrix and the physical validation procedure in
   `android/phone/docs/TOUCH_DEVICE_VALIDATION.md`, adding a new row when the
   platform introduces a distinct posture or input mode.
5. Preserve pointer defaults and the existing Tablet scripting API. A new
   adapter is complete only when the same feature QML works with both the new
   profile and the default pointer profile.
