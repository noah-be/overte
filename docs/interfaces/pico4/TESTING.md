# Test Overte for Pico 4

## Device-free tests

From the repository root:

```bash
./android/vr/pico/tests/pico-device-free-test.sh
```

This checks shell, packaging, WebView, microphone, OpenXR lifecycle, fixture,
device-lock, and power-analysis contracts without ADB or a headset. The broader
hardware-independent suite is documented in
[`android/vr/pico/docs/PICO4_TESTING.md`](../../../android/vr/pico/docs/PICO4_TESTING.md).

## Physical headset

Build verification and device mutation are separate. The device-acceptance
workflow requires an immutable candidate, explicit installation confirmation, a
protected environment, and a dedicated runner with exactly one authorized Pico.
It binds the report to the tag, commit, APK digest, and signing certificate.

A device-free pass cannot establish rendering, controller, audio, thermal,
power, lifecycle, or comfort behavior on a worn headset.

### Personal Alpha core journey

Run this baseline only on an authorized headset. Record the source revision,
APK digest, a non-secret device label, Pico OS version, start/end time, and the
result of every step. Keep account names, USB serials, tokens, and private world
addresses out of committed evidence.

1. Install and launch the selected APK using the documented deploy path.
2. Enter one representative world and confirm useful stereoscopic rendering.
3. Verify head and both-controller tracking, required buttons, pointing,
   selection, and one grab/release interaction.
4. Complete movement or teleport, open and operate the tablet, and enter text
   through the required keyboard path.
5. Verify audio playback and mute. Exercise microphone permission once allowed
   and once denied, confirming that denial fails safely.
6. Exercise pause/resume, headset removal/re-entry, application restart, and a
   clean exit.
7. Continue representative use until the total session reaches 30 minutes;
   record crashes, critical thermal behavior, and observed memory growth.

Stop at the first failure that prevents later steps, record that blocker, and
make it the next repair target. Passing this journey on one named device and
revision is Personal Alpha evidence, not broad Pico compatibility or release
acceptance.
