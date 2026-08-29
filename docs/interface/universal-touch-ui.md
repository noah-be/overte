# Universal touch UI

Overte's touch UI should adapt to the capabilities and usable geometry of a
surface, not to a list of device model names. A device integration supplies a
small capability profile; shared QML derives layout measurements from it.

## Layers

1. `controlsUit/TouchUiProfileBase.qml` defines platform-neutral defaults for
   input, host presentation and available features.
2. A device selector overrides only the capabilities that differ. Each touch
   host provides one selector instead of copying feature screens.
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

The legacy `picoResolutionSettingsAvailable` profile input remains an
implementation detail for compatibility. Shared presentation and E2E code
projects it as the product-neutral `vrRenderResolutionAvailable` capability
and `settings.vr-render-resolution` semantic feature ID.

Shared tablet controls may expose a non-localized `semanticId`, `objectName`
or `semanticScreenId` alongside their translated accessibility description.
These IDs are automation identity, not visible labels. The versioned public
taxonomy and product-policy boundary are documented in
[`tests/device/TABLET_E2E.md`](../../tests/device/TABLET_E2E.md).

Each feature supplies its current `availableWidth` and `availableHeight` to its
presentation object. A host that has not already removed its safe area may
also supply the four inset values directly to `TouchUiMetrics`.

Adapters must not copy a feature screen or redefine feature layout values. A
new touch device starts with one profile selector; device-specific QML should
be added elsewhere only when a hardware or operating-system constraint cannot
be represented by the shared inputs.

An adapter declares direct touch and its presentation mode, then consumes live
host measurements for input capabilities and geometry. Launcher columns and
measurements come from the shared base. Conservative startup values may apply
until the first valid native snapshot arrives.

Runtime measurements are trusted only after platform and native validation.
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

## Runtime pipeline

A platform host observes surface geometry, safe areas, configuration, keyboard
and input-device changes. It validates those measurements before publishing
them through a platform-owned, read-only boundary. Android Phone publishes the
snapshot through `Tablet.touchUiRuntimeMetrics`; an Apple host may instead
expose a native QML singleton. The selected `TouchUiProfile.qml` maps that
boundary to the platform-neutral profile properties. Rotation, window resizing,
keyboard visibility and input-device changes therefore update the open UI
without rebuilding feature screens.

Direct-touch text entry uses the platform input method when available. The
legacy QML keyboard remains available to offscreen hosts. Forms provide
content-specific input hints, scroll the focused field into view when the
keyboard appears and hide it during teardown.

A short, stationary tap activates an enabled button, switch, row or other
actionable control when the finger is released. Controls nested in a scrolling
or paging surface must not lose that tap to the parent gesture recognizer;
movement beyond the drag threshold remains a scroll or page gesture. No action
requires a long press unless it explicitly exposes a separate long-press
command.

## Adoption order

Adopt the foundation one complete user path at a time:

1. system tablet launcher and navigation
2. dialogs, text input and software-keyboard behavior
3. settings controls and preferences
4. avatar, audio and security screens
5. the mobile action bar and remaining platform-specific screens

For each adopted path, move shared measurements into a feature presentation
object, leave only capabilities in the device profile, and add compact,
medium, expanded, font-scale and pointer-compatibility tests before removing
duplicated platform QML.

## Adding another touch device

1. Add one selector-backed `TouchUiProfile.qml` adapter for the platform.
2. Feed validated surface, safe-area, scale, IME and input capabilities into
   that adapter. Reuse `Tablet.touchUiRuntimeMetrics` only when the host owns an
   equally trusted native measurement boundary; otherwise expose a small
   platform-specific read-only provider and map it in the profile.
3. Keep feature flags in the adapter and layout policy in shared metrics or a
   feature configuration. Do not add device-model checks to feature QML.
4. Run the host device matrix and its physical validation procedure, adding a
   new row when the platform introduces a distinct posture or input mode.
5. Preserve pointer defaults and the existing Tablet scripting API. A new
   adapter is complete only when the same feature QML works with both the new
   profile and the default pointer profile.
