# Android Phone development status

## Implemented or host-verified

- independent Phone application and package identity;
- mono 2D renderer and touchscreen input;
- network, audio output, optional microphone, and vibration wiring;
- verified 16-KiB-compatible ARM64 dependency and APK gates;
- separate x86_64 emulator variant;
- device-free behavior, security, packaging, and coverage contracts; and
- store-neutral candidate and emulator-acceptance workflows.

## Remaining physical-device evidence

At least one Adreno and one Mali phone must cover rendering, touch, audio,
keyboard, lifecycle, deep links, page-size compatibility, sustained performance,
memory, battery, thermals, cutouts, and vendor power behavior. A successful
build, emulator launch, or static contract is not equivalent evidence.

Historical nightly implementation notes are retained under `archive/` and are
not current build or release instructions.
