# Pico 4 development status

## Implemented or host-verified

- maintained Linux build and dependency bootstrap;
- dedicated Pico package, OpenXR boundary, and ARM64 APK validation;
- device-free lifecycle, WebView, microphone, input, packaging, and power
  contracts;
- draft release-candidate provenance, SBOM, checksum, and signing gates; and
- separately authorized physical-device handoff.

## Remaining device evidence

Worn-headset validation remains authoritative for rendering, controllers,
interaction, audio, microphone routing, lifecycle, thermals, sustained power,
world loading, and comfort. Store requirements remain external until verified
by an authorized release owner.

Historical nightly implementation notes are retained under `archive/` and are
not current build or acceptance instructions.
