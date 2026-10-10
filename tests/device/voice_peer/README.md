# Linux PC voice-test partner

This is the PC half of a bidirectional physical-device voice lab. It starts one
normal Overte Interface client with a dedicated profile, sends a fresh PCM
challenge through its microphone stream, and captures only its private output
stream. It complements the device-journey milestone; it does not activate a
device suite, Jenkins schedule, merge gate, or mobile capability.

## Requirements and startup

Use Linux with a working user PulseAudio server or PipeWire's PulseAudio
compatibility service, `pactl`, `paplay`, `parec`, Python 3.11+, and a trusted
native Overte executable compatible with the target domain. The controller
uses Python's standard library and needs no Python audio package. Interface
still requires its normal graphical session and runtime libraries.

```bash
python3 tests/device/voice_peer/voice_peer.py start \
  --client /absolute/path/to/interface --domain hifi://overte_hub
python3 tests/device/voice_peer/voice_peer.py status
python3 tests/device/voice_peer/voice_peer.py check-server
python3 tests/device/voice_peer/voice_peer.py stop
```

`start` detaches the controller and waits for a fresh in-client snapshot and
verified private audio streams. `serve` accepts the same options and runs in
the foreground. `status` reports domain/mixer connection separately from
client and audio readiness. `check-server` requires an actual audio-mixer
connection and tests the PC microphone -> domain mixer -> PC output path,
then sends the same signal while muted and requires a quiet, complete capture.
`check-local` instead measures the PC microphone and client-local echo path;
its result explicitly makes no network claim.

The default state directory is `$XDG_STATE_HOME/overte-voice-peer`, or
`~/.local/state/overte-voice-peer`. Set `--state-dir /private/path` **before**
the subcommand to use another directory. The directory must belong to the
current user and is mode 0700. Runtime tokens, profile, and client logs stay
there. A file lock prevents two controllers owning the same state directory.

For repeatable local startup, place a mode-0600 `launch-config.json` in that
directory (or pass `--launch-config`):

```json
{
  "client": "/absolute/path/to/interface",
  "domain": "hifi://overte_hub",
  "clientEnv": "/private/path/client-env.json"
}
```

`clientEnv` is optional. Its mode-0600 JSON object may set `LD_LIBRARY_PATH`,
`QT_PLUGIN_PATH`, `QT_QPA_PLATFORM_PLUGIN_PATH`, `QML2_IMPORT_PATH`,
`QTWEBENGINEPROCESS_PATH`, and `QT_QPA_PLATFORM` for a locally prepared runtime.
Keep executable and library locations outside the repository. With this
configuration, `voice_peer.py start` needs no further arguments.

The owned device fixture retains bounded startup-failure diagnostics under
`voice-peer-diagnostics` in its private fixture output. It still stops its
owned client and releases the audio reservation. Diagnostic files are local,
mode 0600, and are excluded from public device evidence; controller tokens
and generated authenticated runtime scripts are never copied there.

## Device handoff

The PC appears as `OVERTE_VOICE_TEST_PC`. Both avatars must be in the same
domain and close enough for spatial voice. The PC uses the domain's spawn;
move it to the device's test position when necessary:

```bash
python3 tests/device/voice_peer/voice_peer.py position --x 0 --y 2 --z 0
```

For **PC -> device**, generate a fresh challenge first. Prepare the device's
receive capture, then invoke the PC sender with that same challenge:

```bash
python3 tests/device/voice_peer/voice_peer.py challenge --output /tmp/voice-reference.wav
python3 tests/device/voice_peer/voice_peer.py send --challenge CHALLENGE_FROM_JSON
python3 tests/device/voice_peer/voice_peer.py analyze \
  --wav /private/device-received.wav --challenge CHALLENGE_FROM_JSON
```

`send` reports that playback reached the PC microphone probe. It never reports
remote reception as passed. `analyze` must receive the device's actual
recording, not the generated reference.

For **device -> PC**, generate a new challenge WAV and provision it to the
device's microphone-path sender. Start PC reception before the device sends:

```bash
python3 tests/device/voice_peer/voice_peer.py receive \
  --challenge CHALLENGE_FROM_JSON --seconds 8 --expect present
```

`receive` holds the PC muted, disables both echoes, and blocks until capture
and detection finish. Invoke it concurrently with the external device sender.
For a mute control, repeat with the device muted and `--expect absent`.
The optional [voice-roundtrip suite](../VOICE_ROUNDTRIP.md) supplies dedicated
Android, iPad, and Pico test-build sender/capture transports.
Do not substitute `Audio.playSound()` for an avatar microphone-path sender.

## Signal and evidence

Version 1 derives twelve ordered symbols from a fresh 128-bit hexadecimal
challenge. Frequencies are 500, 650, 800, 950, 1100, 1250, 1400, and 1550 Hz;
adjacent symbols differ. Each tone lasts 240 ms with an 8 ms ramp at each edge,
followed by an 80 ms gap. Leading and trailing silence are 500 ms each. The
reference is mono signed 16-bit PCM at 24 kHz, 15% peak amplitude, 4.84 seconds.

Detection requires all twelve symbols in order at their expected relative
times, at least 65% coverage per symbol and 85% average coverage, a full capture,
and less than 1% clipping. It uses 40 ms spectral windows every 20 ms, a -50 dBFS
detection floor, and at least 55% spectral energy at the detected frequency.
Mono and stereo 16-bit PCM at 8-48 kHz are accepted. Channels are evaluated
independently to avoid inverted-stereo cancellation. A mute control requires
a complete capture, no expected pattern, and overall RMS below -55 dBFS.
These thresholds are an initial digital-path baseline, not an acoustic or
speech-quality calibration. A speech fixture is not implemented yet.

Completed operations write `last-result.json`, including the challenge,
detector metrics, client binary SHA-256, reported build identity, runner-source
SHA-256, UTC times, and proof boundary. No fork commit is inferred from an
installed binary's version string. Temporary captured audio is deleted after
analysis; only an explicitly generated reference WAV persists. Failed
infrastructure operations do not overwrite an earlier completed result.

The client starts muted and returns to muted with both echoes off after each
operation. Test processing disables the PC noise gate and echo cancellation
and attenuates injector/system audio; this exercises the baseline voice path,
not default processing quality. Interface gets separate XDG profile paths and
an empty default-script override. The controller creates separate TX and RX
null sinks, verifies streams by the exact owned Interface PID, and never changes
system audio defaults or moves another application's streams. Control listens
only on loopback, authenticates every request with a private token, and exposes
only fixed operations. Stop and normal signal shutdown reap owned processes
and unload only modules whose numeric handles and names still match.

Exit codes: `0` successful operation, `1` audio assertion failure, `2` invalid
configuration, `75` infrastructure failure. A PCM pass does not prove a real
microphone or loudspeaker, mobile audio permissions, or device interoperability.
`check-server` includes only the PC and the domain mixer.

## Verification

```bash
python3 tests/device/self_tests/test_voice_peer.py -v
node --check tests/device/voice_peer/peer.js
python3 tests/run-project-tests.py --profile quick --timeout 240
git diff --check
```

The signal tests cover real PCM at multiple rates, delay, attenuation/noise,
wrong challenges, wrong order, continuous tone, broadband noise, silence,
missing symbols, short/truncated captures, and inverted stereo. Ownership
contracts reject missing/wrong streams, stale snapshots, and reused module
handles. These hardware-free tests run in the quick and full control-plane
profiles. A live PC check remains a separate measured operation.
