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
