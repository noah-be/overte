# iOS microphone request lifetime

The Full Client calls `overteIOSActivateAudioSession()` followed by
`overteIOSRequestMicrophonePermission()` in `AudioClient.cpp`. The existing
Shared shim forwards to `IOSAudioAdapter`, registered by the native source in
the real `Overte` target. This delta preserves SH-006 v001–v003 and the subsequent
cohort-v050 Shared mute bridge already present in the assigned v066 baseline.

The iOS-local `NativeAudioOperations::requestPermission` takes a validity
predicate as well as a completion. `AVAudioOperations` checks that predicate
and UIKit's active application state on the main queue immediately before
`requestRecordPermission`. A skipped queued request completes with `Unknown`;
this releases its slot without treating cancellation as a grant/denial or
reactivating audio.

Only one pending native request is retained. Stop, suspension, interruption,
permission changes and failures invalidate its epoch. Restart/resume cannot
revive it. Its slot survives invalidation until native completion because an
already presented system dialog cannot be dismissed by this adapter. Stale or
duplicate callbacks cannot consume a newer request's slot. Callbacks hold weak
adapter ownership. A scheduling exception releases the slot and reports Failed.

`python3 -B ios/tests/audio-permission-request-test.py` executes the production
adapter and original Shared gate/shim with a held native queue. The same test
with `--baseline ecf6d4135aa70efbd8197976d8fdefe18dabc86b` confirms that the old
adapter still prompts after cancellation. `audio-adapter-test.py` retains the
existing audio transition, failure containment and shim regression coverage.

These are host tests with native operations substituted, plus a source guard
for the real main-queue invocation. They do not compile or execute UIKit,
AVFoundation or the Full Client. Native prompt/foreground ordering, an OS call
already entered concurrently with cancellation, callback latency, capture stop,
routes and both form-factor acceptance remain unqualified. No timeout pretends
to dismiss an unanswered system permission dialog.
