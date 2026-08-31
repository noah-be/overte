# Pico 4 roadmap

- **Priority:** NOW
- **Maturity:** Experimental
- **Last verified:** Host and device-free evidence at `3ba6df421f`,
  2026-08-24, Linux; physical-device evidence is still required

## Current milestone

`PICO-P1` — Personal Alpha: a repeatable private build that completes the
core Overte journey on one named Pico 4 without a critical failure.

## Exit criteria

- [ ] At a named source revision, the documented Linux path builds the ARM64
  APK, installs it on one named Pico 4, and launches it successfully.
- [ ] On that headset, one representative world loads and renders correctly
  enough to complete the core journey.
- [ ] Head and controller tracking, required buttons, pointing, selection, and
  grabbing work for the core journey.
- [ ] Movement or teleport and the tablet, text-entry, and system-keyboard path
  needed by the core journey work on the headset.
- [ ] Playback, mute, microphone permission allowed, and microphone permission
  denied each behave safely and predictably.
- [ ] Pause/resume, headset removal/re-entry, application restart, and clean
  exit do not leave the app in an unusable state.
- [ ] A documented 30-minute headset session completes without a crash,
  critical thermal behavior, or uncontrolled memory growth; known limitations
  are recorded.

## Single next action

Install the APK built from the current `android-vr-pico` candidate on one
explicitly selected Pico 4 and run the documented core-journey baseline,
recording the source revision, device identity, result, and first blocking
failure.

## Blockers

- Physical-device evidence requires an authorized, USB-connected Pico 4 and a
  person able to wear and operate it.
- The device run must name the exact source revision; host and device-free
  evidence cannot replace it.

## Non-goals

- Meta Quest support or validation;
- store submission, public release, or broad hardware compatibility;
- optional trackers, accessories, and full desktop-interface parity; and
- iPad, macOS, or Android phone work before `PICO-P1` is closed or explicitly
  paused.

## Evidence

- [Development status](DEVELOPMENT_STATUS.md)
- [Testing and Pico 4 core journey](TESTING.md)
- [Build and deployment](BUILD.md)
- [Security and privacy](SECURITY_AND_PRIVACY.md)
- [Retained historical notes](archive/README.md)
