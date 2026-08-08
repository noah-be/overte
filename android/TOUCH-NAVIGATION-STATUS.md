# Android Phone Touch Navigation Status

## Implemented and verified

- Phone-specific virtual joystick movement and swipe-to-look mappings.
- Corrected horizontal and vertical swipe direction.
- First-/third-person view button with synchronized camera boom state.
- Stable repeated first-/third-person switching without QML button-state reentrancy.
- Two-finger perspective zoom defaults to disabled.
- The legacy keyboard/mouse pinch path is disabled for the phone build, so the
  navigation preference is the only path that can enable phone pinch zoom.
- Android IME support is enabled only while an actual offscreen QML text field
  has focus. This removes the phantom Android text-selection UI from the normal
  phone viewport while preserving text-entry support.

The disabled pinch state and removal of the phantom text-selection UI were
confirmed manually on a phone build. Host regression tests and Android APK
content, padding, and 16 KiB packaging gates passed.

## Open verification

- Enable the two-finger perspective zoom preference under
  **Settings > General Settings > Navigation** and confirm that pinch zoom
  starts without restarting the app.
- Disable the preference again and confirm that pinch zoom stops immediately.
- Recheck text entry in address, login, and settings fields after the dynamic
  IME gating change.

## Phone/tablet integration

The current `feature/android-phone-support` integration point is merged. The
phone action bar now provides **Go To**, **Tablet**, and **View** controls; the
former action-bar Login slot is used by View, while Login remains available
from Tablet Home. Tablet visibility still captures touch input, hides the
virtual pad and action bars, and restores world controls when closed.

The dedicated phone tablet registrar owns the Settings button. The generic
Settings startup script is deliberately not loaded as well, avoiding duplicate
Settings buttons and mutable QML button-proxy updates.

The combined tablet and touch-navigation host regression suites pass. An
incremental phone build, APK gates, and the open manual verification above are
still required before merging into the phone branch.
