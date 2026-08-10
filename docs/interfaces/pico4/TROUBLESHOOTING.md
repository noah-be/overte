# Troubleshoot the Pico 4 port

Start with:

```bash
cd android
./build-pico.sh doctor
```

Use the phase-specific guidance in
[`android/PICO4_BUILD.md`](../../../android/PICO4_BUILD.md#troubleshooting).

- For a missing dependency bundle, rerun the checksum-verified download and
  prepare phases before building.
- For Gradle failures, use `./build-pico.sh build --stacktrace`.
- For `unauthorized` ADB state, unlock the headset and accept the USB debugging
  prompt.
- With multiple devices, set `ANDROID_SERIAL`; do not rely on ADB's implicit
  target selection.
- Keep raw Logcat, screenshots, device identifiers, and account-related output
  private and temporary.
