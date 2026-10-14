# Pico client apps

The Pico startup selector retains the existing VR services and Create app and
adds **EMOTE** to the normal tablet. It reuses the native QML Emote application
and bundled animations also used by Phone and iOS. No web page is required.

Open the tablet and select **EMOTE** with a controller ray. Select one of the
ten animations; selecting it again stops playback. Selecting another animation
replaces the active one. Leaving the app or reloading scripts restores the
avatar's normal animation. An animation that has not finished loading reports
its loading state instead of starting incomplete playback.

## Host checks

Run from the repository root:

```bash
python3 android/vr/pico/tests/pico4-test-suite.py --test emote --test coverage-matrix --test suite-runner
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software qmltestrunner -input android/vr/pico/tests/qml/tst_pico_emote.qml
```

The JavaScript test verifies startup preservation, local animation resources,
playback, stop and lifecycle cleanup. The Qt Quick test needs Qt 5 Quick Test
and Quick Controls 2; it checks native pointer clicks and visible status at
tablet dimensions. These are host checks. They do not prove controller-ray
delivery, avatar animation visibility to another client, or headset performance.

## Headset acceptance

Bind results to the tested source commit and APK. From a normal launch, verify
that Create and the existing VR apps still appear, that exactly one Emote app
appears, and that each animation starts using a controller ray. Check repeated
selection, replacement, navigation away and script reload. Have a second client
observe the avatar animation; Pico's normal startup hides its local avatar mesh.
Confirm both debug and release configurations when qualifying each artifact.
