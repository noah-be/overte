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
- The Activity follows all sensor orientations and publishes validated live
  surface, cutout, gesture, IME, density, font-scale, hover, keyboard and
  haptics measurements through the native Tablet boundary.
- The action bars adapt between a bottom horizontal portrait layout and a
  vertical landscape layout without entering protected display regions.
- Tablet, address, login, Settings, Avatar, Audio, Security, Emote and menu
  surfaces share touch targets, font scale, scroll physics and accessibility
  activation semantics.

The disabled pinch state and removal of the phantom text-selection UI were
confirmed manually on a phone build. Enabling pinch zoom, saving the preference,
and disabling it again were also confirmed to take effect without restarting.
The phone-specific compact General Settings footer was confirmed to render at
the lower-right with usable button dimensions. Host regression tests and
Android APK content, padding, and 16 KiB packaging gates passed; the final app
process remained running with no fatal entries in the PID-filtered diagnostic.

## Runtime validation

Host policy/component, coverage and mutation gates protect the deterministic
parts of the universal touch stack. Physical IME, cutout, fold, TalkBack and
GPU behavior must be recorded with `TOUCH_DEVICE_VALIDATION.md`; a host pass is
not presented as a device result.

## Phone/tablet integration

The current `android-phone` integration point is merged. The
phone action bar now provides **Go To**, **Tablet**, and **View** controls; the
former action-bar Login slot is used by View, while Login remains available
from Tablet Home. Tablet visibility still captures touch input, hides the
virtual pad and action bars, and restores world controls when closed.

The dedicated phone tablet registrar owns the Settings button. The generic
Settings startup script is deliberately not loaded as well, avoiding duplicate
Settings buttons and mutable QML button-proxy updates.

Phone General Settings now uses a fail-closed category allowlist. It retains
phone pinch navigation and touch-look X/Y sensitivity while excluding the
shared categories that still contain desktop toolbar/tablet, desktop
filesystem, HMD, VR laser/keyboard, Oculus-only, disabled crash-reporting, or
no-op Discord controls. Desktop, Pico, and other VR clients retain their
established categories.

The combined tablet and touch-navigation host regression suites cover the
shared architecture. Merge readiness additionally requires the repository's
normal review process and whichever physical rows are required for the target
release; this status document does not claim that an unrecorded device run
passed.
