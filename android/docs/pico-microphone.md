# Pico 4 microphone investigation

This document records controlled microphone findings for the Pico Interface.
The production Pico path now captures 48 kHz mono PCM through Android's public
`AudioRecord` API with `AUDIO_SOURCE_MIC`, bypassing Qt 5's deprecated OpenSL
ES input plugin. Audio quality and sustained delivery remain separate questions
and the current debug-build throughput limit is described below.

The implementation is Apache-2.0 licensed like the surrounding Overte code.
It uses only Android SDK and JNI APIs; it does not import, link, or redistribute
the Pico SDK or any proprietary Pico microphone library.

## Test controls

The microphone research build supports three opt-in ADB properties:

- `debug.overte.audio_input`: `voicecommunication`, `voicerecognition`, `mic`,
  or `camcorder`;
- `debug.overte.audio_trace=1`: one-second raw input-level, Overte noise-gate,
  and watchdog summaries; and
- `debug.overte.audio_capture_seconds`: capture 1-60 seconds of the exact raw
  Android input delivered to Overte in the app-private cache file
  `pico-mic-input.wav`.

`pico-microphone-test.sh SOURCE [SECONDS] [auto|FAN_PERCENT]` performs a cold
start, verifies the requested source, samples its raw input level, reports fan
RPM and maximum temperatures, then stops Overte and restores automatic fan
control. An omitted fan argument defaults to a fixed 50% for reproducible
short source and speech comparisons. The runner verifies the requested fixed
duty and refuses to start above 72 C CPU or 70 C GPU. These preflight limits
can be overridden with `PICO_MIC_MAX_START_CPU_MC` and
`PICO_MIC_MAX_START_GPU_MC` when a test protocol explicitly requires it. It
first cools a warm headset in up to three ten-second 100% fan intervals during
fixed-fan tests. After each interval it restores the requested duty, waits five
seconds, and repeats the preflight check. It aborts at 90 C CPU or 85 C GPU,
and limits fan-off XR runs to five seconds. A thermally limited run still emits
a CSV row with its actual elapsed time, partial microphone statistics, maximum
temperatures, and `status=thermal_limit`, then returns a failure status.

An `auto` run disables any stale fixed-fan test mode and verifies that actual
fan duty matches the thermal service before launching Overte. If this cannot
be verified, the microphone test does not start. Use `auto` for the final
real-world validation after completing controlled fixed-50% comparisons.

The CSV also reports `gate_blocks`, `gate_open_blocks`, and their weighted
ratio. These describe Overte's adaptive noise gate after Android capture
processing, whereas `mean_level` and `max_peak` describe the raw Android input.

For reproducible host-generated speech, set `PICO_MIC_PLAYBACK_WAV` to a local
WAV file. The runner then enables a raw Pico capture for the requested test
duration and plays the file through the host's default PulseAudio/PipeWire
sink after the newly created Pico capture file proves that the requested
source is recording. `PICO_MIC_PLAYBACK_DELAY` controls the delay before
playback in whole seconds and defaults to one. Playback tests require a
duration of at least ten seconds. This file-based in-run hook avoids racing an
external listener against the heavily flooded Interface log.

The runner also disables Pico's proximity-based sleep for the duration of an
unattended test, refreshes the XR worn/screen state at launch, and clears its
Overte test properties during cleanup. This keeps Qt audio callbacks active
when no person is wearing the headset while preserving the same capture path
used by a normal worn session.

Each run also inspects the active Android AudioFlinger input thread and reports
the numeric and symbolic audio source plus whether Acoustic Echo Canceler and
Noise Suppression are attached. This turns the expected source/effect mapping
into a per-run assertion trail instead of relying only on the requested Qt
device name.

`startup_input_starts` counts actual AudioRecord openings during cold-start
stabilization; `startup_input_reuses` counts same-source selections that
updated UI classification without reopening capture.

The runner polls bounded log snapshots for source readiness instead of waiting
on a streaming `logcat | grep` pipeline. PicOS did not terminate the old
pipeline promptly after a match, which delayed some measurement markers by up
to 14 seconds. Measurement duration now uses a monotonic deadline, includes
ADB temperature-query time, and is delimited by explicit start/end log
markers. This prevents both slow temperature queries and the final live log
dump from adding unreported seconds or frames to a CSV row.

## Initial source matrix

All four sources remained active and delivered roughly 70-109 Qt reads per two
seconds and approximately 100 network audio frames per second. Android routed
all of them as 48 kHz, 16-bit mono input.

| Qt device | Android source | Source ID | AEC | Noise suppression |
| --- | --- | ---: | --- | --- |
| voicecommunication | `AUDIO_SOURCE_VOICE_COMMUNICATION` | 7 | Enabled | Enabled |
| voicerecognition | `AUDIO_SOURCE_VOICE_RECOGNITION` | 6 | Disabled | Disabled |
| mic | `AUDIO_SOURCE_MIC` | 1 | Disabled | Disabled |
| camcorder | `AUDIO_SOURCE_CAMCORDER` | 5 | Disabled | Disabled |

`voicecommunication` is the only tested source for which Android attached its
Acoustic Echo Canceler and Noise Suppression effects. `voicerecognition`, `mic`,
and `camcorder` had no Android capture effects. The saved device configuration
on the test headset was `Audio/VR/INPUT=camcorder`; this explicit user setting
replaced the initially selected `voicecommunication` source during startup.
After completing the comparative tests, the headset's saved input was changed
to `voicecommunication`. A normal cold start without diagnostic properties
then opened it once, reused it for both later selection events, and never
opened `camcorder`.

Ambient observations before the controlled fan run showed the lowest and most
stable levels for `voicecommunication`, moderate levels for
`voicerecognition`, higher sensitivity for `mic`, and the largest gain and
fluctuations for `camcorder`. These observations are directional only because
the room sound was not calibrated.

## Fan-noise isolation

Overte used the same scene, render profile, headset position, and `camcorder`
source while only fixed fan duty changed. Values are arithmetic means of the
one-second raw-input loudness summaries.

| Input source | Fan duty | Fan RPM | Mean raw level | Observation |
| --- | ---: | ---: | ---: | --- |
| camcorder | 0% | 0 | 9.93 | Quiet baseline; stopped immediately after sampling because CPU reached about 94 C. |
| camcorder | 50% | 8,568 | 20.88 | Clearly above the fan-off baseline. |
| camcorder | 100% | 14,284 | 169.26 | Fan dominates the microphone signal. |
| voicecommunication | 50% | 8,525 | 28.40 | No clear benefit at this speed in the changing room ambience. |
| voicecommunication | 100% | 14,245 | 64.83 | Hardware processing reduced the high-speed fan signal substantially, but did not remove it. |

The 0% result is useful only as a brief acoustic reference and must not be used
for longer XR runs. Even 50% allowed CPU temperature to approach 89 C in this
scene. Fixed-fan tests must monitor temperatures, and automatic control must be
restored afterward.

## External-noise scenario

Four 15-second cold-start runs used automatic fan control with uncontrolled
mechanical background noise. Repeating `voicecommunication` on both sides of
the `camcorder` run controls for changing fan speed and background level.

| Input source | Mean raw level | Maximum peak | Fan RPM | Fan duty |
| --- | ---: | ---: | ---: | ---: |
| voicecommunication A | 4.99 | 28.29 | 6,673 | 40% |
| camcorder | 15.43 | 100.48 | 7,373 | 45% |
| voicecommunication B | 4.51 | 23.92 | 7,380 | 45% |
| voicerecognition | 4.64 | 32.08 | 7,390 | 45% |
| mic | 4.96 | 25.57 | 7,398 | 45% |

`camcorder` was the only clear outlier: its mean level was more than three
times the bracketing `voicecommunication` runs, and its maximum peak was more
than four times higher. The other three sources had similar average levels,
but `voicecommunication` also supplies Android hardware AEC and noise
suppression and therefore remains the preferred chat candidate.

Raw-WAV comparison at approximately 7,400 fan RPM showed continuous broadband
noise from `camcorder`. In `voicecommunication`, Android processing introduced
quiet intervals and reduced the measured energy by approximately 14-21 dB in
every tested band from 80 Hz through 16 kHz. Overall full-file mean volume is
misleading for this comparison because intermittent peaks dominate it.

These tests establish background-noise rejection, not speech quality. A later
fixed-phrase test must confirm that `voicecommunication` does not attenuate or
colour nearby speech excessively before it becomes the enforced Pico default.

## Source-selection behavior

The Pico OpenXR display advertises `voicecommunication` as its preferred HMD
input source. This affects a fresh or unset HMD microphone selection; an
explicit source saved by the user remains authoritative. The Android device
picker describes `voicecommunication` as the recommended echo/noise-reduction
choice and warns that `camcorder` has high background sensitivity.

On Android, an unset HMD input is resolved directly to the display plugin's
preferred source. This avoids passing the desktop-only `default ` placeholder
to Qt Android, where it does not name a real device and would stop capture.

This preference is intentionally not an unconditional override. The measured
background rejection strongly supports it as the initial selection, while a
controlled spoken-phrase comparison remains necessary before removing the
user's ability to select another source.

The fresh-profile path was validated on-device by temporarily removing only
the saved HMD input key: `voicecommunication` stayed active across consecutive
watchdog intervals and delivered continuous samples. The original device
configuration was restored after the test. An explicit saved `camcorder`
selection was also verified to remain authoritative.

## Stability and thermal limit

A requested five-minute `voicecommunication` run under automatic fan control
was thermally limited after 76 seconds of level samples while Overte rendered
the test scene. Until shutdown, all 38 watchdog checks reported an active input
with 60-108 reads per two-second interval (mean 95.53), for 7,299 measured
audio frames in total. The safety cutoff triggered at 90.55 C CPU and 76 C
GPU; the app then stopped and automatic fan control was verified. This is a
thermal render-duration limit, not a microphone dropout. Long microphone-only
stability tests require a lower-load scene or another way to suspend XR
rendering without suspending audio.

After all diagnostics and session-reuse changes, a final requested 60-second
integration run reached the thermal limit after 58 seconds. It reported 6,281
gate blocks, a 4.90% gate-open ratio, Android source ID 7, both AEC and noise
suppression enabled, one AudioRecord opening, and two reuse events. The cutoff
occurred at 90.1 C CPU and 74.8 C GPU; cleanup again restored automatic fan
control and stopped the app. The microphone and all assertions remained valid
through the thermally limited run.

### Public Android AudioRecord backend

The Pico Interface now replaces only its microphone capture backend with a
small Java `AudioRecord` worker using source 1 (`MIC`). PCM is copied through a
standard JNI callback into the existing AudioClient path, so local echo,
resampling, loudness reporting, Overte's noise gate, codec selection, and
network packets remain unchanged. The capture worker uses Android's urgent
audio thread priority and blocking reads with a reusable 20 ms buffer.

The bridge is initialized by `PicoInterfaceActivity`, which supplies a stable
application-class-loader reference before AudioClient needs it. Logical Qt
device rediscovery updates the displayed input name without reopening the same
Android MIC session. The watchdog can still restart a genuinely stalled
session. A device test verified source ID 1, no Android AEC or noise suppression,
one real AudioRecord opening, successful level/gate samples, and automatic fan
restoration.

JNI delivery now writes into a mutex-protected, two-second bounded PCM FIFO and
posts at most one pending Qt drain event. AudioClient drains no more than the
capacity of its existing ten-frame input ring per event. This prevents both an
unbounded Qt event backlog and accidental loss inside that smaller ring. The
watchdog uses actual capture callbacks rather than the lower number of batched
drains. `PICO_MIC_TRANSPORT` and the test CSV separately expose captured,
processed, dropped, current-backlog, and peak-backlog PCM frames.

This deliberately does not emulate the historical diagnostic source selector:
all Pico UI input labels currently map to the one verified public MIC source.
The older source-comparison results below remain research evidence, not a claim
that the new production backend opens sources 6 or 7.

### Remaining full-XR debug throughput limit

Before replacement, later unattended tests no longer reproduced the earlier
sustained rate. With
the corrected time window, a five-second `voicecommunication` run delivered
240 frames. Per-second traces began near the expected 100 frames/s for roughly
two seconds, then fell to approximately 13-27 frames/s. The two-second
watchdog's `readyRead` counts fell at the same time, proving that frames are
not discarded by Overtes resampler, gate, encoder, or packet path: Qt/OpenSL
stops delivering sufficient input buffers.

Several controlled exclusions narrowed the problem:

- commit `99e08148e1`, before the merged graphics and physics optimizations,
  delivered 488 frames under the same older, overlong 15-second harness window
  versus 452 for the current branch; the graphics changes are not causal;
- increasing QAudioInput's requested buffer from 20 ms to 100 ms did not
  improve delivery;
- suppressing audio output did not improve input throughput, so shared
  AudioClient-thread output work is not starving input; and
- repeatedly forcing PicOS worn/screen properties did not improve a corrected
  five-second run (218 frames versus the 240-frame baseline).

A diagnostic Qt build processed OpenSL's completed-buffer callback directly
instead of queueing it onto the owning Qt thread. Source 7 improved from 240
to 335 frames in five seconds, confirming that delayed two-buffer queue
replenishment is part of the loss. It still fell well short of 500 frames, and
switching that build to source 1 failed to activate the source. Direct callback
processing races Qt's QBuffer and AudioClient state, so it was rejected and
the original plugin was restored. A production fix needs thread-safe immediate
OpenSL re-enqueueing with copied data delivery, or replacement of the OpenSL
input backend with Android AudioRecord/AAudio.

A temporary Java `AudioRecord` diagnostic, run in the same microphone-granted
APK without Qt or OpenXR, captured source 1 (`MIC`) for 10.004 seconds. It read
942,720 bytes / 471,360 mono frames with no errors, 98.2% of the nominal
480,000 frames. The identical diagnostic using source 7
(`VOICE_COMMUNICATION`) blocked inside even a nominally non-blocking read.
This proves that Pico hardware and Android's basic recording path can sustain
real time, while PicOS source 7 and Qt 5's deprecated OpenSL ES input path need
separate treatment. The temporary Java diagnostic was removed after recording
these results.

The new backend removes that Qt/OpenSL capture bottleneck: the standalone public
API test still obtains 98.2% of nominal PCM and the integrated app receives the
same source successfully. A corrected ten-second FIFO test captured 476,160 of
the nominal 480,000 PCM frames (99.2%) with one AudioRecord opening. Under the
full XR debug workload AudioClient processed 67,200 frames, produced 140 network
frames, reached the FIFO's 96,000-frame/two-second bound, and deliberately
dropped 401,280 oldest frames to prevent ever-growing voice latency. Automatic
fan control was restored after the test.

The batching experiment therefore disproves JNI/Qt event count as the primary
remaining bottleneck. It localizes the problem to integrated AudioClient
processing or scheduling under the full XR debug workload, not Pico hardware,
permissions, proprietary APIs, or Qt's former input plugin. That path must be
profiled stage-by-stage or checked in a release-equivalent build before using
raw WAV duration as a speech-quality result.

## Host-TTS capture check

The file-triggered host playback hook successfully placed the fixed sentence
in the Pico raw capture; the captured speech peaked at -3.52 dBFS. The WAV held
only 3.78 seconds of samples during a much longer wall-clock capture because
of the callback-throughput failure. This validates playback timing and signal
routing, but it is not yet a valid full-phrase quality comparison.

## Overte noise-gate interaction

A bracketing 15-second external-noise comparison measured both raw input and
Overte's default enabled, automatic noise gate. Fan speed remained
approximately 6,600 RPM throughout.

| Input source | Mean raw level | Maximum peak | Gate-open ratio |
| --- | ---: | ---: | ---: |
| voicecommunication A | 7.52 | 35.14 | 4.17% |
| camcorder | 62.09 | 346.01 | 74.98% |
| voicecommunication B | 8.00 | 33.35 | 8.44% |
| voicerecognition | 7.95 | 33.76 | 11.19% |
| mic | 8.41 | 30.25 | 17.28% |

After brief adaptive periods, `voicecommunication` commonly held the software
gate fully closed against the background. `camcorder` held it fully open for
many consecutive seconds and would therefore transmit the background noise
much more often. This establishes that the high-sensitivity source also
defeats the later software gate; it does not establish near-field speech
quality or attack behavior, which still require a controlled spoken phrase.

The active `voicecommunication` Android record thread was independently
verified as 48 kHz mono `AUDIO_SOURCE_VOICE_COMMUNICATION` with no read errors.
Its session had both Qualcomm Fluence Acoustic Echo Canceler and Noise
Suppression registered and enabled. The other tested sources did not receive
those preprocessing effects.

Android device discovery may announce the same physical source first as the
platform default and later as the HMD default. The Pico path reuses an active,
error-free AudioRecord session in that case while updating the UI device
classification. Actual source changes and internal direct restart calls for
format or explicit wake recovery bypass this shortcut; a stopped or errored
input cannot qualify for reuse. Android may also recover a stopped state by
restarting the existing QAudioInput object, as tested below.

On-device cold starts confirmed one real opening plus two reuse events when
`voicecommunication` was already the active source. Selecting `camcorder`
performed the required source change once and reused that session for the
following duplicate selection. Continuous watchdog reads confirmed that reuse
did not stall capture.

In one five-second display-sleep/wake test, two-second input reads fell from
about 100 through 60 and 22 to 7, then recovered immediately to 87 and returned
to roughly 100. A repeated test with explicit recovery tracing recorded 29,
21, and 19 reads during the transition, followed by an Android stopped-state
restart with `NoError`; reads then reached 80 and 102. Recovery therefore does
not require a full device-selection restart. Dedicated trace events identify
both low-read watchdog decisions and Android stopped-state restarts, which are
separate paths.

## Next spoken-phrase test

The remaining decision is speech quality, not background rejection. Run it
in a controlled quiet environment after the headset cools, with automatic fan
control and a fixed speaker-to-headset distance. Record the same short phrase
three times each with `voicecommunication`, `voicerecognition`, and `mic`;
`camcorder` is already excluded as the normal chat choice by the background
results.

Compare consonant attack, word intelligibility, tonal colour, level pumping,
and whether the first syllable opens Overte's automatic gate reliably. A
second pass should play speech from the Pico speakers while recording to check
echo cancellation. Keep source order counterbalanced and retain the raw WAVs,
gate-open ratios, Android effect flags, fan RPM, and temperatures. Only this
test can decide whether `voicecommunication` should remain merely the default
or become a stronger enforced Pico policy.
