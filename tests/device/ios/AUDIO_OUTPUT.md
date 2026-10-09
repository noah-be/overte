<!-- Copyright 2026 Overte e.V. SPDX-License-Identifier: Apache-2.0 -->
# Internal iPad output at volume zero

This physical-device check analyzes the final PCM pulled by Overte's ordinary
Qt audio sink. It works with the iPad's system output volume at zero. It records
output buffers, not microphone sound, and requires no external microphone.
It does not establish that the speaker emits sound.

Use the existing iOS E2E Full Client, private Appium/WDA target and exact
source revision, producer IPA SHA256 and `About.buildVersion`. The candidate
must include `Test.voiceTest` and the read-only `Test.acousticTest` status hook.
The script does not prepare acoustic measurement or enable synthetic input.
Keep the iPad unlocked and use its built-in output route. Set system volume
to zero before testing; the runner observes it and rejects nonzero volume.

Run once with each microphone decision, keeping private target selectors and
fresh result directories outside Git:

```bash
python3 tests/device/ios/audio_output.py \
  --target-config "$AUDIO_TARGET_CONFIG" \
  --listen-address "$AUDIO_LISTEN_ADDRESS" \
  --source-revision "$AUDIO_SOURCE_REVISION" \
  --producer-artifact-sha256 "$AUDIO_PRODUCER_SHA256" \
  --expected-build-version "$AUDIO_BUILD_VERSION" \
  --output "$AUDIO_OUTPUT_DIRECTORY" \
  --reset-microphone --microphone-decision deny \
  --lock-file "$HOME/Documents/github/overte-ipad-windows-vm/.device-test.lock"
```

Then repeat with a new output directory and `--microphone-decision allow`.
The installation and any additional device-lab locks prevent concurrent runs.
When resetting permission, the host explicitly answers the fresh microphone
dialog and verifies that it closed before launching the test script.

The script first checks unmute, mute and unmute again without playing a test
tone. Allow must open active input; Deny and voice mute must close it. It then
mutes the microphone and records four eight-second output captures: a quiet
control and three different fresh twelve-symbol playback challenges. Every
capture requires system output volume exactly zero, with all symbols arriving
in order and bounded clipping. The quiet control must contain none of them.
A meter change alone never passes.

These are separate observations: a device may retain a nonzero minimum volume
in its active microphone session. Such a value is recorded in the permission
transitions and never accepted as a zero-volume PCM capture. No challenge is
played during those transitions. This check does not prove simultaneous live
microphone capture and playback at hardware volume zero.

The test saves and restores the audio settings and stops its owned injector
and output recording. Private WAV payloads are analyzed in a temporary host
directory and expire on-device after 45 seconds. The host verifies their
removal before restarting the normal app and records that restart separately.
Failed cleanup or restart makes the complete run fail. The script also rejects
foreground loss after starting and publishes a fresh, run-bound native foreground
heartbeat. Wi-Fi adapters can verify that heartbeat with the independently
resolved process ID without accessibility snapshots that stall on Qt scenes. `result.json` contains
measurements and candidate identity, without PCM or private device selectors.
Its source/artifact binding is operator-selected provenance, not a cryptographic
attestation of the installed signed bytes.

Verify the host workflow with:

```bash
python3 tests/run-unittest-suite.py tests/device/self_tests --pattern test_audio_output.py
python3 tests/run-project-tests.py --profile quick --timeout 240
git diff --check
```

Host fixtures are not physical-device evidence. The optional
[speaker-to-microphone check](ACOUSTIC_LOOPBACK.md) measures emitted sound and
requires nonzero system volume; it is a separate test.
