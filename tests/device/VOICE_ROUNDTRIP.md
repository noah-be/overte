# Synthetic voice roundtrip

`voice-roundtrip` is an optional extended suite in the existing device runner.
It verifies received PCM for PC-to-device and device-to-PC avatar voice, then
repeats both directions with the sender muted. Each leg uses a new 128-bit
challenge. A send acknowledgement, local injector, retained capture, or local
echo cannot replace a received challenge.

The common module owns assertions. The existing Android Phone/Pico ADB and
iOS Appium adapters deliver `voice.exchange` commands and collect the exact
fresh result. The shared fixture orchestrator owns the domain, PC process,
isolated audio routes and cleanup. Jenkins only selects suites, reserves
resources and publishes the ordinary JSON/JUnit results.

## Dedicated builds

The CMake option `OVERTE_E2E_VOICE_TESTS` defaults to `OFF`. It enables the
bounded `Test.voiceTest` API only in a dedicated build. The API additionally
requires an active `--testScript` launch and `--testResultsLocation`.

In Android product checkouts, build the existing debug variant with
`-PoverteVoiceTests=true`. Release variants force the option off. The existing
debug E2E Activity packages this checkout's probe and uses app-private command
and result files. Set `OVERTE_ANDROID_E2E_DEBUG=1` for the ADB adapter.

In the Apple checkout, `ios/build-ios.sh configure --platform device
--client-graph --world-observations --e2e-test-build --bundle-id YOUR.e2e`
also enables the voice hook. The ordinary non-E2E configure path disables it.
Use the existing signed E2E build, installation, Appium and installed-candidate
binding workflows. This feature does not substitute a runtime version string
for an installed artifact's cryptographic identity.

The synthetic source has its own precise timer on the audio thread and feeds
240-frame network PCM packets through the ordinary mute, noise-gate, encoder
and packet path. Physical/dummy/recorded input callbacks cannot advance the
challenge or send a duplicate stream while test mode owns that clock. A
separate audio gate survives iOS microphone shutdown. The probe disables
noise reduction/AEC, echo and unrelated injectors during this deterministic
test and restores their previous state afterward. Capture uses Interface's
existing final output recording path. Native recording is limited to 6–10
seconds and a watchdog finalizes it independently of the host command channel.

Each challenge starts a fresh monotonic epoch with at most 100 ms of catch-up.
Longer stalls during a challenge fail with `voice-source-clock-late`; incomplete
progress is retained. Idle silence can rebase after preparation, domain joins
or device reconfiguration without advancing the next challenge. Stop,
pause and iOS foreground loss/interruption cancel the source. A native 120-second
lease bounds abandoned test mode, independently of the script watchdog. Valid
commands renew that lease. Failure also mutes physical input until the probe
restores the saved settings. Reset stops the test clock without changing the
ordinary user audio lifecycle.

This checks the digital voice path and mute behavior. Physical microphones,
loudspeakers, OS permission recovery, AEC and noise suppression need their own
tests. Keep their existing suites.

## Local run

Prepare the usual physical target configuration and a private mode-0600 PC
launch configuration described in [voice_peer/README.md](voice_peer/README.md).
The PC agent needs a working graphical session, PulseAudio/PipeWire and the
Overte runtime libraries. Set:

```bash
export OVERTE_E2E_VOICE_TESTS=1
export OVERTE_E2E_VOICE_PEER_CONFIG=/private/pc-launch-config.json
export OVERTE_ANDROID_E2E_DEBUG=1 # Phone/Pico ADB only
python3 tests/device/pipeline.py \
  --adapter-manifest tests/device/adapters/appium/ios.json \
  --platform ios --suite voice-roundtrip \
  --domain-server /absolute/path/domain-server \
  --assignment-client /absolute/path/assignment-client \
  --public-host LAB_PC_ADDRESS --fixture-bind 0.0.0.0 \
  --output-dir /private/new-voice-results
```

Use the appropriate existing Phone/Pico manifest and platform for those
products. Private selectors continue through the existing target mechanisms.
The fixture overrides the launch configuration's domain with its owned test
domain. The standalone PC peer can still use `overte_hub`; repeatable CI uses
the controlled domain to keep ambient audio and unrelated avatars out of mute
assertions. An external fixture provider must own the PC too and supply
`OVERTE_E2E_VOICE_PEER_STATE` through its private environment contract.

The PC waits for mixer readiness. The device joins the same domain and the PC
is positioned next to it. Receive capture starts before transmission; a fresh
PC capture-ready challenge prevents a timing-based assumption. The same PCM
analyzer validates both receivers. Positive legs require all twelve symbols
and bounded clipping. Negative legs require a complete quiet capture.

## Evidence and ownership

`voice-roundtrip.json` contains measurements, challenges, the observed device
version and PC binary/runner digests. The runner supplies the tested checkout,
target binding, module status and JUnit. Failed PCM assertions are product
failures; adapter/fixture failures are infrastructure errors. Cleanup errors
cannot turn an observed product failure into a retryable result.

Raw PCM is retained in private module storage with an exact capture digest for
failure diagnosis; it is excluded from the laboratory's publishable JSON/XML/log
artifacts. Captures contain synthetic lab challenges. Reset
overwrites the private device result, deletes the WAV and restores audio state.
Probe/native watchdogs bound abandoned test state and captures. Process death
is handled by the existing runner/fixture lifecycle.

Device-to-PC measurements also retain available native PC audio stream counters
sampled during reception. These observations help distinguish packet loss,
buffer starvation and dropped frames without changing the PCM verdict.

`voice-native-status.json` retains the latest bounded native status even when a
send fails. Each completed device-to-PC leg also records that status. It includes
clock activity/error, real/dummy/test callback counts, Qt input state/error and
lifecycle/mute observations. iOS adds OS permission separately from capture
eligibility, foreground/interruption and lifecycle outcome. Permission values
are `0=unknown, 1=granted, 2=denied, 3=revoked`; outcomes are `0=stopped,
1=playback-only, 2=capturing, 3=muted, 4=suspended, 5=interrupted, 6=failed`.
Missing Qt input is represented by `-1`. These observations contain no route,
device identifier or free-form native error message. They do not establish a
working physical microphone or repair a native capture failure.

One host lock serializes all owned PC fixtures, including direct local runs.
Jenkins's optional `RUN_VOICE_ROUNDTRIP` stage also holds
`overte-e2e-voice-pc`; lock order is PC audio, profile, device. Supply the private
`VOICE_PEER_CONFIG` path on the Linux agent and the usual domain binaries.
The option defaults off. No job, schedule, promotion evidence or merge gate is
activated by adding this suite.

Hardware-free checks:

```bash
python3 -m unittest discover -s tests/device/self_tests -p test_voice_roundtrip.py -v
python3 tests/device/run_control_plane_tests.py --profile quick
```

The focused tests compile the real native generator and hook with a bounded
audio seam, compare its PCM with the Python reference, execute the actual probe
voice handler, exercise each adapter transport, and reject silent receivers,
stale results, wrong domains and corrupt captures. They do not qualify a mobile
product build or a physical device.
The production clock regression also executes complete muted/unmuted challenges
after actual input shutdown, rejects duplicate physical callbacks and verifies
foreground cancellation, reset, lease expiry and late-clock failure. On the iOS
branch it uses the actual native adapter and Shared bridge with OS calls replaced
by fixtures; on other branches it substitutes the unavailable native owner.
