# Meta Quest roadmap

- **Priority:** PARKED
- **Maturity:** Experimental and hardware-unverified
- **Last verified:** Source and documentation inventory at `bf43162ffa`,
  2026-08-24, host-only; no current physical-headset evidence

## Current milestone

`QUEST-Q0` — Paused hardware gate: preserve the existing port without active
feature work until one named Quest headset is available and the target is
explicitly resumed.

## Exit criteria

- [x] Quest work is preserved on its dedicated permanent product branch.
- [x] The paused state, missing hardware evidence, and product-order boundary
  are documented without claiming support.
- [ ] One exact Quest model and OS version are named and authorized for testing.
- [ ] At a named source revision, the current build installs and launches on
  that headset through a revalidated developer path.
- [ ] A representative world renders and the required head/controller tracking,
  locomotion, selection, and interaction work on the headset.
- [ ] Audio, mute, microphone allow/deny, pause/resume, restart, and clean exit
  behave safely on the headset.
- [ ] A documented 30-minute headset session completes without a crash,
  critical thermal behavior, or uncontrolled memory growth.

## Single next action

Obtain or arrange authorized access to one explicitly named Quest headset; only
then change this roadmap from `PARKED` and revalidate the current build path.

## Blockers

- No physical Quest test hardware is currently available.
- Virtual and simulated testing is too indirect and time-consuming to replace
  headset acceptance.
- Pico 4, Android Phone, and iPad are the ordered active product tracks.

## Non-goals

- Active Quest feature development while the target is parked;
- treating Pico 4, emulator, simulator, or legacy GVR results as current Quest
  evidence;
- store submission, public distribution, or broad Quest-model support; and
- optimizing virtual test infrastructure solely to avoid the hardware gate.

## Evidence

- [Quest status and support boundary](README.md)
- [Device-test adapter](../../../android/vr/quest/device-tests/README.md)
- [Retained legacy GVR evidence](../../../android/vr/quest/docs/LEGACY_GVR_EVIDENCE.md)
- [Repository portfolio roadmap](../../ROADMAP.md)
