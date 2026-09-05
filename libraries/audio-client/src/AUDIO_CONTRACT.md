# SH-006 v003: notify failed native stop for additional containment

This supersedes v002 for iOS consumers only. AudioLifecycleGate and the four
virtual native methods/global overteIOS entry symbols are unchanged. Phone/Pico
may stay on v001. The delta adds:

- `overte::audio::notifyIOSAudioStateChanged()` for native permission, route,
  interruption and foreground changes after committing current gate/OS state.
- `setIOSAudioStateCallback(std::function<void()>)`, owned by AudioClient. Native
  adapters call notify only; they must not replace the Shared callback.
- Actual AudioClient.cpp/h hookup: queue onto the audio thread, recheck current
  lifecycle and permission, close live Qt input on deny/revoke/mute/suspend,
  clear the input ring/loudness, notify UI, and reopen a permitted default input
  on grant/resume/unmute/route change. Activation precedes permission request.

Native implementation must attempt bounded OS capture stop on revoke/interruption/
background BEFORE notify; queued Qt work is not an immediate native stop. On
success, notify the committed non-capturing state. On OS failure or timeout,
commit a fail-closed state (microphonePermissionGranted returns false), then
ALSO notify. This is a failure observation, never a successful-stop receipt.
Shared's existing refresh then closes its Qt source and clears buffers as an
additional containment action. Keep native cleanup/recovery pending until actual
completion; do not revive capture merely to clear Failed. Native code must not
suppress this failure notification while waiting for another transition.
The tested existing notify API is sufficient; no new native signature is needed.
The
microphonePermissionGranted method must reflect current capture permission AND
foreground/interruption state, never OS grant alone. Mute closes the actual Qt
input, not only sample processing. The callback only queues Qt work; it must not
reenter callback registration or call native OS. Callback unregistration waits
for an in-flight enqueue before AudioClient::stop/destruction; stale queued work
checks the current lifecycle. Registration remains process-wide single-adapter.

Import this v003 delta AFTER v002 on an iOS integration branch. It changes the
contract and adds an executable failure-state callback test only; v002's actual
Shared AudioClient close/ring-reset path already handles permission=false.
The original v002 single-commit patch was applied after v001.
Its parent is an exact v001 import over apple-ios
0122d0211ad69172a4c71d2c4226d904a192770d. Full AudioClient files are exported for
inspection but never overwrite newer owner changes; General owns these files.
This is a Shared iOS runtime worktree, separate from the main source contracts
and immutable Cold Build. No artifact is relabeled with this source SHA.

Validation: C++14 native shim/gate tests and concurrent callback-unregistration
check PASS. Three explicit source-wiring tests check activation ordering,
queued callback/teardown, and actual input close/reopen. Those checks are NOT
full Qt compilation, AVAudioSession execution or a device capture-stop proof.
Qt backend synchronous stop latency, native finite-stop enforcement, all route/
buffer/cadence and hardware results remain pending. v002 closes the source
callback gap without claiming those acceptance gates. PX-16 remains separately
required for Shared/native diagnostic sinks.
