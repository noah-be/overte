# Pico accessibility equivalence — PI-007

Revision 09 implementation handoff, not a blanket N/A or hardware PASS.

| Surface/journey | Implemented source behavior | Deferred observation |
| --- | --- | --- |
| Native startup | Stable startup_status ID, localized text, polite live region; decorative icon/progress excluded; scalable text and color-contrast check | Actual Pico accessibility service, font scaling and announcement |
| Home/Settings | Existing app.settings/nav.home/nav.back and audio/controllers/general/security IDs retained by Pico policy; SH-003 selector and retained preference enforcement consumed | Custom Shared QML label/order/hit-area/focus enforcement and world-space legibility |
| HMD/render controls | HMD preferences and VR render resolution remain required, not hidden as Phone-only exemptions | Pointer reachability, contrast and controller activation |
| Text fields | External keyboard routing plus native WebView commit/composition, Unicode deletion, single-editor focus and lifecycle cleanup | Worn-headset VR keyboard, caret geometry, selection/replacement and IME variants |
| Close/cancel | Window/item focus loss relinquishes input ownership; existing nav.close remains the semantic Shared contract | Physical cancellation sequence without movement/look leakage |
| Hands | Existing required function/active/valid-joint gates retained; no new route enabled | A separate authorized experimental trial; never substitute for required controllers |

The source/UI-policy tests validate only these declared bindings. A physical
PI-004 checkpoint still must review each core control and text journey. Shared
QML changes belong to General; no duplicated platform QML profile is introduced.
Full scanner/semantic snapshots and accessibility-service equivalence are not
inferred from Android XML attributes or from the computed startup color ratio.

SH-003 retained-preferences/v001 (source c15e7fa5a824143eccd28b3b321a33073dbf7691,
release manifest 5b57da3f101266f87e263e4283f39a711882d9121d2f7001d7f4f54fa84f176b)
binds the real shared Preferences registry, typed persistence/trigger methods
and both original retained Preference.qml components. Pico's actual Gradle
product define selects the same configuredProduct used by FileUtils and
Preferences. HMD, VR Movement, Controllers, Dominant Hand and User Interface
remain allowed; Plugins, Snapshots, Privacy and unknown categories are omitted
and cannot be persisted through a direct Preference pointer. Hidden descendants
cannot receive focus through these bases. No native override or duplicated
category allowlist is needed. This is not an authorization gate for arbitrary
Settings/script calls and does not cover custom controller/graphics pages.
