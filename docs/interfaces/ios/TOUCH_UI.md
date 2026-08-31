# iOS touch UI adapter

The iPhone and iPad client uses the shared, platform-neutral touch UI. The iOS
adapter supplies native runtime metrics and platform capabilities; it does not
maintain a separate copy of the tablet layouts.

## Adapter boundary

The adapter consists of:

- `interface/resources/qml/controlsUit/+ios/TouchUiProfile.qml`, the iOS QML
  selector profile;
- `interface/src/IOSTouchUiMetrics.h` and `IOSTouchUiMetrics.mm`, the native
  read-only metrics provider; and
- `interface/src/Application_Graphics.cpp`, which registers that provider as
  the `OverteIOS 1.0` singleton `IOSTouchUiMetrics`.

The selector order in `libraries/shared/src/shared/FileUtils.cpp` gives `ios`
priority and then retains the existing Phone presentation as a fallback. The
iOS profile therefore overrides platform behavior while continuing to use the
shared touch controls and layouts.

`IOSTouchUiMetrics` publishes live safe-area insets, software-keyboard state and
bottom inset, surface dimensions, display density, and Dynamic Type font scale.
The profile also declares iOS capabilities such as direct touch, haptics, and
screen-space presentation. Shared QML consumes those values without device-model
checks or iPhone/iPad layout forks.

Hardware-keyboard capability is currently conservative and fixed to false. A
future native input-capability adapter should replace that default before
external keyboard and hybrid pointer support can be considered complete.

## Validation matrix

Simulator checks are useful regression evidence, but final acceptance requires
at least one supported physical iPhone and one supported physical iPad.

| Area | Required coverage |
| --- | --- |
| Compact phone | iPhone portrait and landscape, including a notched/Dynamic Island safe area |
| Tablet layouts | iPad portrait and landscape, window resizing, Split View, and Stage Manager where supported |
| Text scaling | Dynamic Type at 1.0, 1.3, 1.5, and above the UI's supported cap |
| Software keyboard | Show, hide, frame changes, focus transfer, and unobscured focused controls |
| Geometry changes | Rotation, safe-area changes, and live surface-size updates |
| External input | Hardware keyboard and pointer behavior, including transitions back to direct touch |
| Accessibility | VoiceOver navigation, labels, focus order, and minimum touch-target usability |

Record failures with the source revision, device and OS version, orientation or
window mode, text size, keyboard state, console excerpt, and a privacy-reviewed
screenshot. The native bootstrap simulator smoke test proves the Apple bundle,
lifecycle, and basic input path only. It does not prove that the experimental
integrated Qt/Overte client renders or operates the complete shared touch UI.

Follow [Testing](TESTING.md) for the executable test commands and physical-device
evidence boundary.
