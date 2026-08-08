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

## Integration required before merging

The current Android phone and tablet feature branches contain a newer system
tablet implementation that is not yet integrated here. In particular, they add
the visible Tablet action-bar button and phone tablet-app registration while
touch navigation adds the View button and related camera handling in the same
files.

Before merging this branch into the current phone base:

1. Merge or rebase onto the agreed current Android phone integration point.
2. Resolve the phone action bar by retaining both the Tablet and View buttons.
3. Retain the tablet visibility/touch-capture behavior from the tablet work.
4. Retain the pinch preference, camera-boom synchronization, and static View
   button behavior from this branch.
5. Run host regressions, an incremental phone build, APK gates, and the open
   manual verification above.

Do not resolve this overlap by copying one complete action-bar version over the
other; each branch currently owns distinct required behavior.
