# macOS roadmap

- **Priority:** PARKED
- **Maturity:** Hosted Intel runtime-verified; physical gameplay hardware and
  native Apple Silicon acceptance incomplete
- **Last verified:** Hosted macOS/Intel evidence retained at `f180de6318`,
  2026-08-24; no current physical-Mac Personal Alpha evidence

## Current milestone

`MAC-P1` — Paused Personal Alpha: resume only when one named physical Mac is
available, then complete the core Overte journey on that machine without a
critical failure.

## Exit criteria

- [ ] One physical Mac, its architecture, macOS version, and intended graphics
  path are named and authorized for testing.
- [ ] At a named source revision, the documented path builds, bundles, installs,
  and launches `Overte.app` on that Mac.
- [ ] One representative world connects, loads, and renders usefully through a
  hardware-accelerated graphics path.
- [ ] Keyboard, pointer, camera, movement, tablet, text-entry, and one
  representative object interaction complete the core journey.
- [ ] Playback, mute, microphone permission allowed, and microphone permission
  denied each behave safely and predictably.
- [ ] Background/foreground, application restart, navigation recovery, and
  clean exit do not leave the app in an unusable state.
- [ ] A documented 30-minute physical-Mac session completes without a crash,
  critical thermal behavior, or uncontrolled memory growth; known limitations
  are recorded.

## Single next action

Obtain or arrange authorized access to one explicitly named physical Mac and
record its architecture and OS version; only then move `MAC-P1` out of
`PARKED` and select a candidate revision.

## Blockers

- No physical Mac test hardware is currently available.
- Hosted, virtualized, and software-renderer testing is too time-consuming and
  cannot replace physical gameplay acceptance.
- Pico 4, Android Phone, and iPad are the ordered active product tracks.

## Non-goals

- More virtual/software-renderer tuning while the target is parked;
- treating hosted Intel or capability-probe results as physical-Mac Personal
  Alpha evidence;
- signing, notarization, installer creation, store work, or public support; and
- broad Intel and Apple Silicon coverage before one named Mac passes `MAC-P1`.

## Evidence

- [Development status](DEVELOPMENT_STATUS.md)
- [Testing and hardware evidence boundary](TESTING.md)
- [Build](BUILD.md)
- [Continuous integration](CI.md)
- [Online loading telemetry](ONLINE_LOADING_TELEMETRY.md)
- [Security and privacy](SECURITY_AND_PRIVACY.md)
