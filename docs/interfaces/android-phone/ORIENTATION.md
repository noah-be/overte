# Android Phone orientation contract

The Android Phone Activities declare `android:screenOrientation="fullSensor"`.
The application therefore does not force landscape and Android may rotate it
through all sensor-reported phone orientations. This source contract is
separate from physical-device qualification.

| Classification | Current contract |
| --- | --- |
| Supported | Normal full-screen landscape is the primary developer and Personal Alpha acceptance layout. Both landscape directions must preserve safe insets and reachable core controls. |
| Tolerated, not yet qualified | Portrait and reverse portrait are intentionally accepted by `fullSensor`. Responsive Phone controls must reflow and the lifecycle must remain bounded, but broad physical-device, cutout, IME and rotation evidence is still pending. |
| Unsupported / no claim | Fixed-orientation guarantees, foldable posture behavior, freeform or split-screen production support, non-phone form factors, and any claim that source-level reflow proves physical-device acceptance. |

Documentation must not describe portrait as disabled or impossible while the
manifest uses `fullSensor`. It may describe portrait as experimental or
unqualified. Emulator evidence also cannot establish physical cutout, vendor,
GPU, thermal, audio or page-size behavior.
