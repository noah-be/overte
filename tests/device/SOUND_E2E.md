# Sound loading and playback E2E contract

The `sound-smoke` suite proves the strongest sound-specific behavior exposed by
the current Interface scripting APIs without recording audio. It uses the
repository-owned network fixture, the in-client test probe, and the shared
`sound-playback` module. Desktop/Oculix targets with the injected probe command
channel advertise this suite; other real adapters remain gated.

## Controlled signal

[`fixture/audio/overte-e2e-tone.wav`](fixture/audio/overte-e2e-tone.wav) is a
deterministically generated 2.0-second, 440 Hz sine wave at 20% amplitude. It is
mono, signed 16-bit little-endian PCM at 8,000 Hz and is 32,044 bytes including
the WAV header. Its SHA-256 is
`e9492f9ed0356257540e6295e1928d9561ff11db1866087d7921f62ea0d3ebd5`.
[`fixture/generate_sound_fixture.py`](fixture/generate_sound_fixture.py)
reproduces the file using only the Python standard library. The non-native
sample rate intentionally exercises `SoundProcessor::interpretAsWav()` and the
`AudioSRC` conversion to Overte's internal 24 kHz rate.

The fixture serves the file at `/audio/overte-e2e-tone.wav` with
`Content-Type: audio/wav`, `Cache-Control: no-store`, and a content length. Its
privacy-safe request telemetry records only method, fixture path, E2E command
query, status, MIME type, byte count, timestamp, and sequence. It never records
audio input or arbitrary request bodies. `/audio/invalid.wav` and ordinary 404
responses support decoder and URL failure contracts.

## Evidence chain

The module requires all of these independent observations:

1. `sound.play` acknowledges the exact random command ID and controlled URL.
   This acknowledgment alone is not playback evidence.
2. The probe observes that same command ID and URL.
3. Fixture telemetry observes a completed HTTP 200 request for that uniquely
   tagged URL, `audio/wav`, and a positive number of delivered bytes. HTTP 200
   alone is not resource or playback evidence.
4. The probe observes `SoundObject.downloaded === true` and the expected
   positive duration. In production, `Sound::soundProcessSuccess()` sets this
   state only after the URL-selected WAV decoder and resampler have produced
   `AudioData`; downloaded bytes alone cannot set it.
5. The probe observes a real injector from `Audio.playSound()` and then its
   productive `AudioInjector.playing` property becoming true. A successful
   call alone cannot pass the module.
6. The injector remains playing in at least two probe snapshots whose
   `sampleSequence` and `sampleEpochMs` both strictly advance.
7. The productive `AudioInjector.finished` signal is observed, `playing` is
   false, and the probe classifies the result as natural completion or an
   explicitly requested stop.
8. `app.process` retains exactly the same non-empty identity before, throughout,
   and after playback.

Snapshots are rejected if sound state is internally impossible, if sequence
and timestamp disagree, or if they regress. The module keeps only JSON state
and controlled fixture metadata; it performs no microphone, loopback, or host
audio capture.

## Capability boundary

`sound.play` is a separate semantic adapter operation because a target-specific
transport must deliver a play command to the running test probe. It must not be
implemented as `asset.load`, `scene.load`, tablet input, or other UI input. For
the network fixture, the command endpoint is polled directly by the probe; an
adapter implementation can post the versioned command there and must
return only `{requested: true, commandId: string}`. The probe and request
telemetry remain the independent acceptance evidence.

The deterministic mock and explicitly controlled Desktop/Oculix profiles
advertise `sound.play`. Desktop copies the repository probe into private target
state, tells that running probe the exact fixture command endpoint, and leaves
resource/injector state entirely to the probe. Other product adapters are
deliberately unchanged.

## Proof boundary

Passing proves that Interface requested the controlled bytes, its production
sound resource reached decoded and usable state through the WAV path, and an
in-client local-only injector started, remained active in fresh observations,
and ended without an Interface process restart.

It does **not** prove that samples traversed the final client mixer, an operating
system audio backend, a selected audio device, an amplifier, or a loudspeaker,
and it does not prove that audible sound reached the room. `localOnly: true`
avoids dependence on a domain audio mixer but does not strengthen the physical
output claim.

A future optional `audio-output.capture` capability could correlate the
controlled waveform and timing through an OS loopback device or host capture.
For targets without trustworthy loopback, a lab-only capability would need a
calibrated microphone or electrical measurement device, isolation from user
audio, explicit privacy controls, and non-archival processing. Neither
capability is defined or implied by `sound-smoke`.

## Device-free verification

The mock downloads and parses the real fixture WAV before advancing its state
machine. Focused tests cover the passing lifecycle plus HTTP 404, invalid WAV,
never-ready resource, injector-not-started, early injector end, process restart,
stale samples, and inconsistent samples:

```bash
python3 -m unittest tests/device/self_tests/test_sound_playback.py -v
```
