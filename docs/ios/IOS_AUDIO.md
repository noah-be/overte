# iOS Full Client audio

The integrated iOS client uses Qt Multimedia for capture and playback,
AVAudioSession for lifecycle and routing policy, and WebRTC audio processing for
the explicit acoustic echo cancellation stage.

## Runtime contract

- AVAudioSession uses `PlayAndRecord`, `GameChat`, default-to-speaker and
  Bluetooth-HFP. It requests a 48 kHz device rate and 10 ms I/O duration and
  records the actual negotiated values.
- Overte's network audio remains 24 kHz, signed 16-bit PCM in 10 ms frames.
  AudioClient resamples at the device boundary.
- Initial iOS output allocation is two network frames (20 ms). Starvation can
  increase the setting; the sink is reopened so the new allocation takes effect.
- WebRTC AEC uses mobile mode. AVAudioSession does not add a second
  application-controlled processing pass.

## Lifecycle and recovery

`start` is the one-time initialization boundary. UIKit background transitions
enqueue `suspend`; foreground transitions enqueue `resume`. Neither transition
blocks the main thread. `stop` is final, null-safe, and idempotent.

An interruption-began event closes Qt input and output while retaining the
logical device selection. `ShouldResume` reactivates AVAudioSession and reopens
both devices only if the application lifecycle is active. Route changes reopen
the system defaults. A media-services reset reapplies the session configuration
before reopening Qt I/O.

Microphone permission fails closed. Undetermined and denied states use the
silent input timer, allowing receive-only operation. A grant callback switches
to the default microphone automatically. On return from Settings, `resume`
rechecks permission; the Audio settings screen shows waiting or denied state.

## Diagnostics and privacy

Expected markers are lifecycle state, coarse permission state, numeric session
event/reason, negotiated rate/buffer duration, and adaptive buffer frame count.
Do not add route names, Bluetooth identifiers, device serials, peer addresses,
tokens, or raw device logs to acceptance artifacts.

## Verification status

Host contracts verify source ownership, queue boundaries, observers, permission
recovery, UI exposure, format constants, AEC mode, and the adaptive buffer path.
Simulator automation may exercise allow/deny/reset transitions but cannot prove
real microphone capture, HFP routing, AEC quality, or latency. Those release
gates remain pending until the matrix in
`ios/tests/audio-device-acceptance.json` is executed on physical iPhone and iPad
hardware. The prepared simulator precheck is
`ios/ci/interface-audio-simulator-e2e.sh`; its output explicitly records
`physicalAudioValidated: false`. No physical-device acceptance was performed as
part of this change.
