# Pico 4 microphone investigation

This document records controlled microphone findings for the Pico Interface.
The Android microphone permission is granted and Qt receives continuous 48 kHz
mono input from every tested source. The current problem is therefore audio
quality and source selection, not permission or loss of capture.

## Test controls

The microphone research build supports two opt-in ADB properties:

- `debug.overte.audio_input`: `voicecommunication`, `voicerecognition`, `mic`,
  or `camcorder`; and
- `debug.overte.audio_trace=1`: one-second raw input-level, Overte noise-gate,
  and watchdog summaries;
  and
- `debug.overte.audio_capture_seconds`: capture 1-60 seconds of the exact raw
  Qt input to the app-private cache file `pico-mic-input.wav`.

`pico-microphone-test.sh SOURCE [SECONDS] [auto|FAN_PERCENT]` performs a cold
start, verifies the requested source, samples its raw input level, reports fan
RPM and maximum temperatures, then stops Overte and restores automatic fan
control. It aborts at 90 C CPU or 85 C GPU, and limits fan-off XR runs to five
seconds. A thermally limited run still emits a CSV row with its actual elapsed
time, partial microphone statistics, maximum temperatures, and
`status=thermal_limit`, then returns a failure status.

The CSV also reports `gate_blocks`, `gate_open_blocks`, and their weighted
ratio. These describe Overte's adaptive noise gate after Android capture
processing, whereas `mean_level` and `max_peak` describe the raw Qt input.

Each run also inspects the active Android AudioFlinger input thread and reports
the numeric and symbolic audio source plus whether Acoustic Echo Canceler and
Noise Suppression are attached. This turns the expected source/effect mapping
into a per-run assertion trail instead of relying only on the requested Qt
device name.

`startup_input_starts` counts actual AudioRecord openings during cold-start
stabilization; `startup_input_reuses` counts same-source selections that
updated UI classification without reopening capture.

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
classification. Actual source changes, stopped inputs, errors, stereo-format
changes, and wake recovery still perform a full restart.

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
