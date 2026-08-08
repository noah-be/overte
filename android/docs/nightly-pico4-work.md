# Nightly Pico 4 work

This log covers autonomous, device-free work based on
`origin/feature/pico4-support`. Branches are stacked in the order listed. No
headset, ADB, Android device, external domain, or device setting is used.

## 2026-08-08

### 01 — WebView frame lifecycle

- Branch: `nightly/pico4-01-webview-frame-lifecycle`
- Commit: recorded after commit creation below
- Change: accept valid transparent WebView frames instead of treating a
  transparent centre pixel as an unready surface; reject invalid dimensions,
  multiplication overflow, null direct-buffer addresses, and undersized JNI
  frame buffers before constructing a `QImage`.
- Regression: `python3 android/tests/pico-webview-bridge-test.py`.
- Passed: WebView bridge regression (2 tests); microphone runner mocks (11);
  unattended runner mocks (9); serverless fixture integrity; Pico device-lock
  mocks (5); Bash syntax for `android/tests/*.sh` and `android/*.sh`.
- Risk: the source-level bridge test cannot exercise Android WebView rendering
  or the Qt scene graph. The checks are deliberately narrow and complement an
  Android build and later acceptance test.
- Pico 4 validation: **not executed**. Load both an opaque page and a page with
  a transparent centre/background, verify content away from the centre renders,
  resize each entity repeatedly, then delete it during active rendering and
  check logcat for JNI/WebView errors or stale frames.

## Cumulative remaining device validation

1. Web entity transparent-content, resize, destruction, and navigation checks
   described above.
2. Both-controller hover, click, drag, scroll, target-loss, and stuck-input
   checks from `pico4-web-entities.md`.
3. Microphone speech quality, AEC/echo, restart, source switching, and sustained
   automatic-fan tests from `pico-microphone.md`.
4. Grab latency and fast trigger/grip transitions with physical OpenXR input.
