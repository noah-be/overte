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

Four eight-second captures cover a quiet control, local playback, local playback
with voice muted, and playback after unmuting. Each playback uses a different
fresh twelve-symbol challenge. All symbols must arrive in order with bounded
clipping; the quiet control must contain none of the challenges. Muting the
microphone preserves local playback while the native permission and input
state must agree with the selected decision. Allow must open active input;
Deny and voice mute must close it. A meter change alone never passes.

The test saves and restores the audio settings and stops its owned injector
and output recording. Private WAV payloads are analyzed in a temporary host
directory and expire on-device after 45 seconds. The host verifies their
removal before restarting the normal app and records that restart separately.
Failed cleanup or restart makes the complete run fail. `result.json` contains
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
