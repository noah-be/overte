# Shared iOS mute caller integration

AudioClient::setMuted forwards iOS mute transitions through overteIOSSetAudioMuted
before its existing Qt refresh and outward notification. iOS calls from other
threads queue to the AudioClient owner. The Apple startup path forwards the
initial mute value before session activation. Existing Pico policy and Apple
Qt callback differences remain intact; no Apple startup implementation is copied
into the other variants.

IOSAudioSessionAdapter has a virtual muted(bool) entry. The existing real
IOSAudioAdapter::muted override is reached without changing platform source.
Legacy adapters inherit conservative deactivation on mute; they do not gain a
functional unmute/resume implementation from that fallback. The current iOS
adapter maintains mute state through activation and supplies the full behavior.

Tests execute the complete actual AudioClient::setMuted method with real Qt
owner-thread/queued calls, signal counting and queued-object destruction. On
Apple they reach the actual Shared bridge and IOSAudioAdapter; only native OS
operations and Qt input refresh are substituted. The exact Apple startup session
segment is also executed, preserving initial mute before activation. The other
variants use a test adapter because they do not contain the Apple implementation.
Missing bridge, missing queue and missing initial-value mutations each fail.
The existing Apple adapter/shim and Main Pico policy checks still pass.

This is not full AudioClient startup/timer/device execution, native AVAudioSession
capture-stop latency, permission hardware, cross-platform runtime qualification
or full SH006/original39 acceptance. Native state and capture resource lifetimes
remain platform acceptance gates. No physical audio access or app build occurs.
