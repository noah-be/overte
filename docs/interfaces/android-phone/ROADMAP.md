# Android Phone roadmap

- **Priority:** NEXT, after `PICO-P1`
- **Maturity:** Emulator-verified and build-ready; physical-device acceptance
  incomplete
- **Last verified:** Host and x86_64 emulator evidence at `d22f491e9c`,
  2026-08-24, Linux; physical-device evidence is still required

## Current milestone

`PHONE-P1` — Personal Alpha: a repeatable private build that completes the
core Overte journey on one named ARM64 Android phone without a critical
failure.

## Exit criteria

- [ ] At a named source revision, the documented Linux path builds the ARM64
  APK, installs it on one named phone, and launches it successfully.
- [ ] One representative world loads and renders usefully in the primary
  landscape layout, including the named device's cutout and safe areas; the
  tolerated portrait path does not crash or expose unreachable core controls.
- [ ] Touch movement, camera control, selection, and one representative object
  interaction work for the core journey.
- [ ] Tablet controls, text entry, and the Android system keyboard remain usable
  through focus and resize transitions.
- [ ] Playback, mute, microphone permission allowed, and microphone permission
  denied each behave safely and predictably.
- [ ] Background/foreground, deep-link entry, application restart, and clean
  exit do not leave the app in an unusable state.
- [ ] A documented 30-minute device session completes without a crash, critical
  thermal behavior, uncontrolled memory growth, or an unusable battery/power
  response; known limitations are recorded.

## Single next action

After `PICO-P1` is complete or explicitly paused, name one available ARM64
Android phone and run the physical-device baseline from an exact
`android-phone` candidate revision, recording the first blocking failure.

## Blockers

- `PICO-P1` is the active product milestone and must complete or be explicitly
  paused before Android Phone becomes the primary track.
- Runtime evidence requires an authorized physical ARM64 Android phone; emulator
  evidence cannot satisfy `PHONE-P1`.

## Non-goals

- Adreno-plus-Mali coverage or a broad device matrix, which belongs to
  `PHONE-V1`;
- production qualification of portrait/reverse-orientation layouts, 32-bit
  devices, store publication, and release support;
- iPad, macOS, Quest, or optional feature-parity work during `PHONE-P1`; and
- treating emulator success as physical-device acceptance.

## Evidence

- [Development status](DEVELOPMENT_STATUS.md)
- [Testing](TESTING.md)
- [Build and deployment](BUILD.md)
- [Orientation contract](ORIENTATION.md)
- [Security and privacy](SECURITY_AND_PRIVACY.md)
- [Retained historical notes](archive/README.md)
