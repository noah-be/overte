<!-- Copyright 2026 Overte e.V. SPDX-License-Identifier: Apache-2.0 -->
# Internal iPad acoustic loopback

This optional physical-device check plays a fresh twelve-symbol tone sequence
through Overte's ordinary local sound injector and detects it in the same iPad's
built-in microphone input. No external microphone or speaker is required. It
complements the [synthetic voice roundtrip](../VOICE_ROUNDTRIP.md): that test
verifies network voice and mute, whereas this check exercises the acoustic path.

## Candidate and prerequisites

- Build the iOS Full Client with `OVERTE_E2E_VOICE_TESTS=ON`. This is an explicit
  test-build option, disabled by default. A build containing only the earlier
  `Test.voiceTest` hook, including build 739, cannot run this new check.
- Use the existing physical-device Appium/WDA installation and a private target
  JSON containing exactly one enabled iOS target. This runner never installs or
  signs an app. Retain the candidate's source revision, producer IPA SHA256 and
  exact `About.buildVersion` separately from the target selector.
- Put the iPad in a quiet room, with its built-in speaker and microphone
  unobstructed, and its system volume above zero. Disconnect external audio
  routes. Native route observations reject Bluetooth, headphones and simulators.
- The test PC needs Python 3.11 or newer. Give the runner one local IPv4 address
  reachable from the iPad. Its temporary HTTP server serves only the generated
  test script, without private configuration, recordings or directory listings.

## Run

Keep the private target configuration outside Git and use a new private evidence
directory for each run. Populate these environment variables from the selected
candidate and local lab configuration:

```bash
python3 tests/device/ios/acoustic_loopback.py \
  --target-config "$ACOUSTIC_TARGET_CONFIG" \
  --listen-address "$ACOUSTIC_LISTEN_ADDRESS" \
  --source-revision "$ACOUSTIC_SOURCE_REVISION" \
  --producer-artifact-sha256 "$ACOUSTIC_PRODUCER_SHA256" \
  --expected-build-version "$ACOUSTIC_BUILD_VERSION" \
  --output "$ACOUSTIC_REPORT_DIRECTORY" \
  --lock-file "$HOME/Documents/github/overte-ipad-windows-vm/.device-test.lock"
```

The runner also holds the local IPA installation lock. Supply any additional
device-lab lock through another `--lock-file` argument; concurrent device runs
must use the same locks. When orchestrated by Jenkins, operate the enclosing job
through the official `overte-jenkins` CLI.

The default preserves the existing microphone permission. If a first request
appears, the runner explicitly selects **Allow** and verifies that the dialog
closed before further test actions. To exercise a fresh first request, append
`--reset-microphone`. That reset targets the foreground Overte app only, waits
for the dialog, answers it, and refuses to continue if it did not close. Select
`--microphone-decision deny` to deny an encountered dialog. Denied permission
cannot establish acoustic playback acceptance because the reference microphone
is then unavailable; the run reports failure rather than overriding that choice.
Unrelated system dialogs are never automatically accepted.

## Measurement and cleanup

The runner launches the local tutorial, away from network voice. The script
waits for granted permission and UIKit foreground, saves the original audio
settings and disables local/server echo, push-to-talk, noise reduction and
Overte AEC. The challenge is explicitly non-spatial local playback, so it uses
the system injector gain at 0 dB; other audio gains are suppressed. It cannot
be attenuated by the avatar's distance from the world origin. The native iOS
adapter temporarily selects `measurement` mode to
minimize system processing, then waits for a stable, active physical input.
System output volume is observed and retained, not changed.

1. Capture eight seconds of actual microphone input without playing a test tone.
   The fresh control sequence must be absent; ambient sound need not be silence.
2. Capture another eight seconds and play a different fresh sequence locally.
   All twelve frequency symbols must be recognized in the correct order and
   timing, with bounded clipping. A level-meter change alone never passes.
3. Restore the saved audio settings and the native session's ordinary mode.
   Stop the owned injector, discard native capture buffers and confirm cleanup.
   Only a successful cleanup permits a passing result.

Input is copied only from `processMicAudioInput`, before echo, AEC, gating and
resampling. It is never copied from the output mixer or synthetic voice source.
The iOS input uses Qt's default ring capacity rather than the smaller network
callback size: native hardware blocks must fit without dropping samples.
Each capture is bounded to ten seconds maximum and checked against its original
format and native route revision. Permission/lifecycle/route changes, missing
input, truncated captures, another nonce or an active synthetic source fail.

`result.json` retains measurements, candidate identity, observed build version
and cleanup status. Raw WAVs are analyzed in a temporary private directory and
are not retained by the host. The on-device transfer payload expires after
45 seconds. The host verifies that this payload has been removed before its
normal app relaunch, so termination cannot cancel the expiry timer. A script
watchdog restores settings on failure; a native watchdog
also bounds capture/injector ownership. The runner never terminates an unfinished
probe before it has reported successful restoration. An infrastructure failure
without a cleanup receipt must not be described as restored.

The result binds the operator-selected source/artifact to the reported installed
build version; it does not attest the installed signed bytes. A passing run
proves the joint built-in speaker-to-microphone path under these test conditions.
It does not calibrate sound pressure, assess subjective speech quality or verify
normal voice processing with AEC enabled. Permission denial and effective voice
mute remain separately recorded checks. This runner does not update or close
GitHub issues.

## Host verification

```bash
python3 tests/run-unittest-suite.py tests/device/self_tests --pattern test_acoustic_loopback.py
python3 tests/device/contracts/audio/test_ios_input_buffer.py
python3 tests/run-project-tests.py --profile quick --timeout 240
git diff --check
```

The focused suite compiles and executes the production capture methods, physical
input wiring and gated `Test.acousticTest` API with OS/injector fixtures. It also
executes the actual JavaScript workflow and checks PCM detection, fresh nonces,
permission-dialog ordering, rejection paths and cleanup. Host fixtures provide
no physical-device evidence; the new iOS candidate must still be built and run.
