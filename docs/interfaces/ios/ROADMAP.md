# iPad and iOS roadmap

- **Priority:** NEXT, after `PHONE-P1`
- **Maturity:** Simulator-verified bootstrap; integrated client experimental;
  physical-device acceptance incomplete
- **Last verified:** Bootstrap and simulator evidence at `92c21c3b13`,
  2026-08-24, macOS/Xcode CI; integrated physical-iPad evidence is still
  required

## Current milestone

`IOS-P1` — iPad Personal Alpha: a repeatable private build of the integrated
Overte client that completes the core journey on one named physical iPad
without a critical failure.

## Exit criteria

- [ ] At a named source revision, the integrated client—not only the
  bootstrap—builds, signs, installs, and launches on one named iPad.
- [ ] One representative world connects, loads, and renders usefully on that
  iPad.
- [ ] Touch movement, camera control, selection, and one representative object
  interaction work in the intended iPad layout and safe areas.
- [ ] Tablet controls, text entry, and the iPadOS system keyboard remain usable
  through focus, resize, and supported orientation transitions.
- [ ] Playback, mute, microphone permission allowed, and microphone permission
  denied each behave safely and predictably.
- [ ] Background/foreground, deep-link entry, application restart, and clean
  exit do not leave the app in an unusable state.
- [ ] A documented 30-minute iPad session completes without a crash, critical
  thermal behavior, or uncontrolled memory growth; known limitations are
  recorded.

## Single next action

After `PHONE-P1` is complete or explicitly paused, name one available iPad and
attempt a signed integrated-client build, installation, and launch from an
exact `apple-ios` revision, recording the first blocking failure.

## Blockers

- `PICO-P1` and then `PHONE-P1` have priority before iPad becomes the primary
  product track.
- The integrated client still has open Qt, V8, MoltenVK, rendering, multimedia,
  and native-dependency gates.
- Runtime evidence requires an authorized physical iPad plus a Mac/Xcode and
  signing environment; simulator or bootstrap evidence cannot satisfy
  `IOS-P1`.

## Non-goals

- iPhone acceptance or a broad iPhone/iPad hardware matrix;
- App Store submission, public distribution, and release support;
- treating the UIKit/Metal bootstrap as the complete Overte client; and
- macOS or Quest development while those targets are paused for lack of
  physical test hardware.

## Evidence

- [Development status](DEVELOPMENT_STATUS.md)
- [Testing and physical-device boundary](TESTING.md)
- [Build and signing](BUILD.md)
- [Touch UI validation](TOUCH_UI.md)
- [Security and privacy](SECURITY_AND_PRIVACY.md)
