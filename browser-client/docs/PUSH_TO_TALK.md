# Desktop Push-to-Talk

This implementation connects the authentic native Audio tablet Desktop PTT switch to browser microphone transmission. The current source passes the genuine twelve-stage synthetic-audio journey in stock Chromium154 and Firefox156; physical microphone and human-audibility evidence remain pending. See [exact current-source evidence](../../docs/browser-client/evidence/tablet-ptt-current-shipping-stock-20261002.json). It changes no microphone permission, native device selection, VR mode, domain rights, heartbeat deadline or audio size/backpressure bound.

## Source basis

The reviewed native source is `f91d15a08587dcd37c642234424b3215dd331724`. `interface/src/scripting/Audio.h` exposes `pushToTalkDesktop` and `pushingToTalk`. In `Audio.cpp:108–129`, unmuting while not held disables native Desktop PTT. `Audio.cpp:207–222` enables PTT in the muted state. `Audio.cpp:487–500` uses the actual held flag for native output ducking and mute/unmute. Therefore this adapter sets the actual held flag before unmute; it does not repeatedly force unmute during a release. The packaged `interface/resources/qml/hifi/audio/Audio.qml:210` renders the authentic `Push To Talk (T)` control.

Native source SHA-256:

- Audio.cpp: `c4eb8bcb34144dff29a587f187de095edf75473aa6bd3fefe98d3bd53b988e4f`
- Audio.h: `55a269802388916686369a01e1c16ad8df628ea33152a36fda757d9f9ac1a3c5`
- Audio.qml: `4208e7f17c85d1c1bd57e515eb191fa6afb1ffb517b5506d58844922e8f99379`

## Admission and ownership

Version 1 command/status DTOs use the current positive permission revision and a bounded monotonic sequence. Browser and gateway transmission require explicit microphone permission, current connection and actual effective native state. Release disables browser transmission synchronously, before its native command; stale held acknowledgments cannot reopen it. The native adapter remains on the existing Script interval and existing bounded authority-captured output queue. Native Qt signal callbacks only mark state dirty. Approval changes, domain changes, navigation, hidden page, window blur and teardown release a held press. Mode changes do not silently acquire or re-enable microphone permission.

The final safe-integer sequence is reserved for release. Session limits, PCM alignment/size, native playback backlog and approval gates are retained. No new native timer, generic native setter, account preference copy or cross-session state is introduced. Full diagnostics and passive diagnostics must be preserved when applying the narrow bridge/server hunks.

An already granted browser microphone remains owned across press/release; only its transmission gate changes. The existing browser mic button remains the explicit permission/arm action. While Desktop PTT is enabled, T holds talk with Tablet closed; the ordinary Tablet button remains available. Editable controls and contenteditable fields do not trigger this shortcut.

## Required real acceptance

Use only the owned managed test domain and two authenticated isolated browser sessions, with source/build/native-library attestations and unchanged baseline cleanup. Open the genuine native Audio page and identify the visible `Push To Talk (T)` control using capture-bound read-only widget geometry; do not guess coordinates or use an Audio setter as the user action. Toggle it with genuine Qt input and require effective versioned state. Explicitly grant the browser microphone, close Tablet, then use actual T key down/up. Require native effective held/mute status and received peer audio only during the held interval, including release-tail refusal. Repeat window blur, hidden page, Tablet open, leave and fresh rejoin; ensure no late held audio. Toggle off through the genuine UI and verify ordinary bidirectional voice still works after explicit unmute. Preserve existing synthetic-core and hardware permission tests.

The CPU tests exercise actual production adapters and handlers with controlled external audio APIs. They do not prove Qt signal timing, microphone hardware, duck gain, real peer audio or native UI calibration. Arbitrary native scripts switching mode during a hold and HMD/device selection remain outside this candidate.

## CPU validation

`node --import tsx --test tests/push-to-talk.test.ts` (13 cases); `node --test gateway/push-to-talk-wire.test.mjs` (3 actual-handler cases); native-output/native-navigation/native-people-ignore/session-races (17 existing cases); `npx tsc --noEmit`; `node --check` on native helper/bridge/server.
