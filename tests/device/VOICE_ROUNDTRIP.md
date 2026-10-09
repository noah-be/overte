# Android Phone synthetic voice roundtrip

`voice-roundtrip` ports the existing iOS device/PC voice test to Android Phone.
It is an optional extended suite in the existing device runner. Four legs check
received PCM: PC-to-Phone and Phone-to-PC, then both directions with the sender
muted. Each leg uses a fresh 128-bit challenge. Send acknowledgements, local
echo and retained captures cannot replace the received challenge.

The module, PC fixture, signal generator, analyzer and probe are adapted from
the iOS implementation at `f4e1ba60c1` (initial suite `27a5da180d`). No iOS
product branch is merged into Android. The existing Phone ADB and controlled
Android Appium transports carry `voice.exchange` through app-private debug
files. The Phone installed-candidate wrappers continue checking the selected
APK; a runtime version string does not establish artifact identity. This port
does not advertise the capability for Pico or iOS targets.

## Dedicated debug build

First prepare the prerequisites and verified 16 KiB dependencies in the
[Phone build guide](https://github.com/noah-be/overte/blob/android-phone/android/phone/docs/BUILD.md). From `android/phone`,
with a JDK from 17 through 21 selected, build:

```bash
../common/gradlew --settings-file settings.gradle \
  -PoverteVoiceTests=true :phoneInterface:assembleDebug
```

`OVERTE_E2E_VOICE_TESTS` defaults to `OFF`. The property enables it in the
Phone debug variant. Release and emulator variants force it off. The native
`Test.voiceTest` API additionally requires an active `--testScript` launch and
`--testResultsLocation`. The existing debug E2E Activity packages the probe and
uses app-private command/results files. Install and bind the exact debug APK
through the existing candidate workflow before running a physical test.

The synthetic source owns a precise timer on the audio thread and feeds
240-frame packets through the normal mute, audio gate, encoder and network
path. Physical, dummy and recorded callbacks cannot advance the challenge or
send a duplicate stream. A separate test gate survives microphone shutdown.
The clock uses monotonic time, permits at most 100 ms of catch-up and fails
larger stalls with `voice-source-clock-late`. Stop and audio pause cancel it;
a native 120-second lease bounds abandoned test mode. Failure mutes input
until the probe restores the saved user settings.

The probe disables noise reduction/AEC, local/server echo and unrelated
injectors during the test and restores them afterward. Capture uses the
existing final output recording path, is bounded to 6–10 seconds and has an
independent native watchdog. This tests digital voice and mute behavior;
physical microphone/speaker audibility and permission recovery remain separate.

## Local run

Prepare the normal private physical Phone target configuration and the
mode-0600 PC launch configuration in [voice_peer/README.md](voice_peer/README.md).
The PC needs a graphical session, PulseAudio/PipeWire and the runtime libraries.
Use a controlled Appium target with `scene.kind=android-debug-e2e`,
`probe.kind=android-run-as` and the existing `clientControl` contract, or use the
Phone ADB manifest:

```bash
export OVERTE_E2E_VOICE_TESTS=1
export OVERTE_E2E_VOICE_PEER_CONFIG=/private/pc-launch-config.json
export OVERTE_ANDROID_E2E_DEBUG=1
python3 tests/device/pipeline.py \
  --adapter-manifest tests/device/adapters/android-phone/adapter.json \
  --platform android-phone --suite voice-roundtrip \
  --domain-server /absolute/path/domain-server \
  --assignment-client /absolute/path/assignment-client \
  --public-host LAB_PC_ADDRESS --fixture-bind 0.0.0.0 \
  --output-dir /private/new-voice-results
```

For Appium, use `tests/device/adapters/android-phone/appium.json` and the usual
private target configuration. Candidate-bound runs use a private manifest with
the existing verifier arguments; see the [Phone adapter guide](adapters/android-phone/README.md).
Private device selectors remain in those existing target mechanisms.

The fixture owns the domain, PC process, isolated audio routes and cleanup.
It overrides the PC launch configuration's domain. The PC waits for mixer
readiness and is placed next to the device. Receiver capture starts before
transmission; a fresh PC capture-ready challenge confirms readiness. Positive
legs require all twelve symbols and bounded clipping. Muted legs require a
complete quiet capture. An external fixture provider must own the PC too and
supply `OVERTE_E2E_VOICE_PEER_STATE` through its private environment contract.

## Evidence and verification

`voice-roundtrip.json` records the four measurements and observed versions.
The runner retains checkout/target identity, module status and JUnit.
`voice-native-status.json` retains bounded clock/input/lifecycle diagnostics,
including failures. Received-PCM assertion failures are product failures;
transport/fixture failures are infrastructure errors. Cleanup failure preserves
an already observed product failure.

Raw PCM stays in private temporary storage. Its digest is checked before
analysis, and raw audio never enters publishable module artifacts. Reset
overwrites the private result, deletes the WAV and restores audio state.
Native/probe watchdogs bound abandoned source and recording state. The existing
runner/fixture lifecycle handles process death.

One host lock serializes owned PC fixtures. Jenkins's optional
`RUN_VOICE_ROUNDTRIP` stage supports the Phone `appium-android` profile and also
holds `overte-e2e-voice-pc`, before profile/device locks. Provide
`VOICE_PEER_CONFIG` on the Linux agent and the usual domain binaries. It defaults
off; this change does not activate a job, schedule or merge gate.

Hardware-free checks from the repository root:

```bash
python3 -m unittest discover -s tests/device/self_tests -p test_voice_roundtrip.py -v
python3 -m unittest discover -s tests/device/self_tests -p test_voice_peer.py -v
python3 tests/run-project-tests.py --profile quick --timeout 240
git diff --check
```

The focused checks compile production native generator, clock/input/shutdown
methods and the scripting hook with bounded device seams, compare PCM with the
Python reference, execute the probe handler and exercise both Android
transports. They reject stale/corrupt captures, wrong domains, clock failures
and silent receivers. They do not establish a complete Android build or a
physical-device pass.
