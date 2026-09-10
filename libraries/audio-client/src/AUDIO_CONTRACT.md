# SH-006 audio gate and existing iOS caller seam v001

Functional implementation contract; no audio artifact/hardware acceptance.
`AudioLifecycleGate.h` is C++14, thread-safe state only. Outcomes are Stopped,
PlaybackOnly, Capturing, Muted, Suspended, Interrupted, Failed. Permission is
Unknown/Granted/Denied/Revoked. Initial state is stopped and not foreground.
Explicit start plus foreground permits playback; only Granted and unmuted,
uninterrupted, active state permits capture. Permission callbacks use the ticket
from beginPermissionRequest; latest-only completion consumes it. Stop, suspend,
interruption and permission revocation invalidate pending tickets. No retry
loop, buffer, raw sample, identifier or private route is retained.

Native adapters serialize actual OS operations and must apply stop/revoke/mute
to actual capture, not merely report a gate value. `mayActivate()` allows a muted
session for playback; it does not authorize capture. `outcome()==Capturing` is
the capture condition. Failed activation calls fail(); explicit start retries;
there is no automatic retry. Native stop has a platform-enforced finite timeout;
report Failed if it cannot stop, never claim Stopped from a timeout alone.
Do not infer successful OS activation from the state model.

## iOS existing production binding

The exact apple-ios source 0122d0211ad69172a4c71d2c4226d904a192770d
already compiles `IOSAudioPermission.mm` via libraries/audio-client/CMakeLists.txt
and calls its four overteIOS functions from AudioClient.cpp. This release
replaces that Shared-owned implementation with a tested fail-closed forwarding
shim while preserving all four signatures and symbols. General integrates the
replacement; iOS owners must not independently edit those Shared paths.

iOS implements `overte::audio::IOSAudioSessionAdapter` in an ios/audio native
file, includes the pinned IOSAudioPermission.h and AudioLifecycleGate.h, and
registers once before AudioClient starts:
`installIOSAudioSessionAdapter(std::make_shared<NativeAdapter>())`.
The exact four virtual methods are in the header. Null or duplicate registration
returns false. Missing registration returns false for permission/activation/
deactivation and drops permission requests. No old AVAudioSession behavior is
silently used. Shared-pointer loads preserve lifetime without holding a mutex
across native operations. Catch native exceptions; no exceptions may cross the
adapter boundary. The native implementation owns its main-queue dispatch,
AVAudioSession configuration, route/interruption/app-state observation and
permission prompt; use the supplied gate for callback cancellation and outcomes.

Do not define the four global overteIOS functions in ios/audio: only the Shared
shim defines them. iOS's existing CMake source entry continues to select the
shim; add only the concrete adapter source to the iOS target. The current main
base lacks the apple-ios AudioClient/CMake changes; the exact existing apple-ios
caller stack is a pinned source prerequisite, not evidence of a main build.
For local native development compile against this release's exported headers
and shim; stage any complete caller integration through General.

Phone/Pico may consume the same state gate in their native audio bridge. They
retain their platform routes and entry symbols; do not adopt the iOS registry.
All diagnostic output uses PX-16 v001 closed events, not OS errors or route IDs.

## Validation and pending gates

C++14 `lifecycle-gate-test.cpp` tests stale/duplicate permission completion,
denial/revoke, suspend, mute, interruption, stop and failure. Compile the .mm
shim as C++ with `-x c++` together with `ios-shim-test.cpp` to test the actual
four entry points, absent/duplicate binding and forwarding. The fake is test-
only; it is not AVAudioSession evidence. Native compilation, buffer/cadence,
route changes, stop-timeout, actual capture revocation, SH-002 acceptance and
downstream audio checkpoints remain pending. Publish a new immutable version
for changed method signatures or outcome semantics.
