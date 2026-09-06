# Pico SH-006 native audio consumer

PI-005/PI-007 implementation. v001 source 29f71fdf41347c3816d0b1ab18ee2b22a9519600,
manifest 62d485618616d47ce95750c34efddcc1584c0856dccf505a3c826eb554337396.
The exact Shared patch is a separate import; its iOS shim is not built by Pico.

PicoAudioLifecycle.cpp uses the original C++ gate, not a Java schema clone.
The actual Shared caller now also consumes sh006-pico-audio/v001, source
f6e709419c571a8f34e47098394ed6c9fd58f347, manifest
d6388d52bc09a90e1cf8196aa57f2d7227088b614c1cd1445821ef0515351520.
Java setMuted, current Activity visibility, permission callbacks and bridge
initialization publish nativePolicyChanged from external policy observations.
Allow requires current foreground, unmuted, a freshly checked OS permission,
the native bridge and safe completed driver cleanup. Missing bindings deny.
Revoke during a read immediately publishes deny before dropping the returned
buffer. Native policy invalidates Shared epochs/FIFO and schedules its real Qt
refresh. Mute/focus loss publish deny before waiting for OS cleanup.

The old Java saved-request/visibility reopen has been removed. Only Shared
refresh owns reopening, including late first focus after an initial dummy input.
Internal start/stop effects do not republish eligibility and cannot feed a
restart loop. Duplicate visibility still rechecks OS permission; the Shared
epoch gate coalesces unchanged policy. Activity callbacks reject stale Activity
owners. A failed driver/read denies until a fresh external policy observation;
failed cleanup still prevents a new recorder. No policy state proves activation.
If bridge reinitialization fails while an earlier Activity's recorder is still
active, Java first publishes deny through the existing bridge, then disables it
and runs bounded stop. A JNI-injected initialization failure regression verifies
that this path does not leave the prior Shared epoch or test recorder active.

PicoAudioShutdown runs driver stop/release on one cleanup worker, bounds the
caller's wait to 1000 ms per cleanup, and prevents opening another recorder
while cleanup is pending or failed. Capture join timeout and driver exceptions
produce failure, not AudioStopped. Unexpected capture exits also use bounded
cleanup. A stalled driver worker may remain alive; this is reported as failed,
not proof that the OS stopped or released its hardware. Further capture is
refused until a successful outstanding cleanup has completed; an unsuccessful
cleanup requires process recovery. Native gate state is authorization, not OS
activation evidence. No microphone samples or route IDs are logged.

Tests execute the production JNI gate and the exact Shared policy callback body
in a real JVM, using a test-only Qt queue and controllable AudioRecord substitute.
They exercise late focus, mute, duplicates, stop without policy feedback, revoke
during blocking read, absent owner/permission error, missing JNI binding and
blocked cleanup/no second recorder. Original Shared tests cover native epochs,
FIFO callback and source caller wiring. All Pico Java sources compile against
the Android SDK. None of this executes a physical Android microphone.

Shared now checks epochs at enqueue/drain/process/network-frame boundaries and
clears residual input/loopback data on policy change. Raw microphone WAV capture
is disabled; a debug property cannot grant recording consent. Complete Qt/JNI
link, real audio-thread/driver/frame cutover latency, route/interruption and
permission behavior, hidden/re-entry and retained-output privacy scans remain
integration/hardware checkpoints. An already executing frame cannot be retracted
by a flag. Start/stop monitor contention is not a proven finite hardware bound.

Run `python3 android/vr/pico/tests/device/test_audio_lifecycle.py`.
The live binding check is `python3 android/vr/pico/tests/device/test_audio_policy_binding.py`.
