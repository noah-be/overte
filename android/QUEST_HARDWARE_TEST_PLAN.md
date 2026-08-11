# Quest hardware acceptance plan

Use this checklist for the first physical Quest 2, Quest Pro, Quest 3, or Quest
3S session. Record headset model, OS version, APK SHA-256, test domain, and the
result of every item. A successful build alone does not make the port usable.

## Preparation

1. Enable developer mode and confirm `adb devices` reports exactly the intended
   headset as `device`.
2. Run `./build-quest.sh build` and retain `reports/quest/verification.json` and
   `size.md` with the test notes.
3. Install with:

   ```bash
   adb install -r apps/picoInterface/build/outputs/apk/debug/overte-quest-preview-debug.apk
   ```

4. Clear Logcat, then capture it for the entire session. Never include access
   tokens or private domain URLs in a public issue.

## Smoke test — release blocker

- The application appears in the unknown/developer sources library and starts
  in immersive VR without returning to Quest Home.
- Both eyes render the same scene with correct projection, scale, and head pose.
- Head tracking remains stable while turning and walking within the guardian.
- Both Touch controllers are detected; pose, trigger, grip, thumbstick, primary
  buttons, menu action, and haptics map correctly.
- Recenter produces a usable forward direction and floor height.
- Microphone denial does not prevent startup; granting it enables voice input.
- Spatial audio plays without severe latency, distortion, or channel reversal.
- The client connects to a known domain, loads an avatar, and can move and
  communicate with a desktop client.
- Web and QML surfaces render and accept pointer input.
- Removing the headset, resuming, opening the system menu, and returning to the
  app do not lose tracking, audio, input, or the OpenXR session.
- Normal exit and forced close do not leave a crash loop on the next launch.

## Stability and performance

- Run for at least 30 minutes in a representative populated domain.
- Record average frame rate, visible judder, application/GPU frame timing,
  memory pressure, thermal warnings, and battery drain.
- Exercise teleport/walking, avatar changes, a web entity, a media surface,
  voice, mute/unmute, and repeated suspend/resume.
- Confirm Android reports no native crash, ANR, tombstone, or repeated OpenXR
  error in Logcat.

## Compatibility matrix

Repeat the smoke test on every supported headset generation that can be
obtained. Treat controller bindings, refresh rate, permissions, and lifecycle as
device-specific until observed. Test a clean install as well as an upgrade over
the previous preview APK.

## Evidence and pass criteria

Attach the verification JSON, size report, sanitized Logcat, screenshots or a
short recording, and concise reproduction steps for failures. The preview is
hardware-validated only after all smoke-test blockers pass on at least one
Quest. Broader support claims require the same evidence for each listed model.
