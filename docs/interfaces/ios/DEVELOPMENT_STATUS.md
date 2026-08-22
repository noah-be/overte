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

## Deferred touch acceptance after the rendering gate

Do not start this work until physical-device rendering is accepted. The shared,
main-based fixes from `fix/universal-touch-ui-tablet-qml` must then be integrated
from main rather than duplicated on `apple-ios`:

- tablet startup and direct touch interaction: `55da2d017e`, `2361d3a9b5`;
- shared TextField context fix: `54d6103edc`.

Validate on both iPhone and iPad that tablet icons appear, short taps work,
swipes do not trigger icons, and Goto/Login/other text fields open the iOS
system keyboard on a short tap. Also validate focus, keyboard geometry, safe
areas, and resize behavior.

There is a separate orientation-product conflict to resolve first: Android
acceptance requires the touch app to start and remain landscape regardless of
Auto-Rotate, while the current iOS matrix still requires portrait/landscape
rotation, Split View, and Stage Manager. Decide the desired orientation for
iPhone and iPad separately before implementing or testing an iOS orientation
lock. Shared Touch UI contract changes originate from main; only any remaining
native iOS focus, keyboard, or orientation adaptation originates from
`apple-ios`.
