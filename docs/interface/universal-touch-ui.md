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
- `screenSpacePresentation` and `screenSpaceContentScale`
- `safeInsetLeft`, `safeInsetTop`, `safeInsetRight`, and `safeInsetBottom`
- feature capabilities such as `graphicsSettingsAvailable` or
  `scriptingPluginsAvailable`

Each feature supplies its current `availableWidth` and `availableHeight` to its
presentation object. A host that has not already removed its safe area may
also supply the four inset values directly to `TouchUiMetrics`.

Adapters must not copy a feature screen or redefine feature layout values. A
new touch device starts with one profile selector; device-specific QML should
be added elsewhere only when a hardware or operating-system constraint cannot
be represented by the shared inputs.

The Android phone selector is the reference adapter. It declares direct touch,
screen-space presentation, haptics and the absence of a hardware keyboard. Its
launcher columns and measurements come from the shared base.

## Responsive contract

The initial width classes use logical QML pixels:

- compact: less than 600 usable pixels
- medium: 600 through 839 usable pixels
- expanded: 840 usable pixels or more

Usable size excludes safe-area insets. Direct-touch controls use a minimum
rendered target of 48 pixels. `Button`, `Slider`, `Switch`, `CheckBox`, and
`TextField` convert that target into local coordinates when a screen-space host
scales the complete QML surface. Feature layouts may be denser on pointer-only
surfaces, but they must not infer input capabilities from width alone.

## Adoption order

Adopt the foundation one complete user path at a time:

1. system tablet launcher and navigation
2. dialogs, text input and software-keyboard behavior
3. settings controls and preferences
4. avatar, audio and security screens
5. the mobile action bar and remaining platform-specific screens

The launcher/navigation, settings/preferences, avatar, audio and security paths
now follow this contract. For each additional path, move shared measurements
into a feature presentation object, leave only capabilities in the single
device profile, and add compact, medium, expanded and pointer-compatibility
tests before removing duplicated platform QML.

## Native follow-up

The current Android Phone profile contains the measured inset and content
scale used by the existing screen-space host. `WindowRoot.qml` exposes all four
insets to `TabletScriptingInterface.cpp`, so asymmetric cutouts are already
supported without native constants. A subsequent Android integration can feed
live `WindowInsets` and logical display density into the profile/host boundary;
feature screens and presentation policies will not need to change.
