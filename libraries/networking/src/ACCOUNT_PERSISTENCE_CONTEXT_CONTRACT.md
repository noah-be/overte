# Protected-account failure invalidates credential completion

PX-15 / SH-005, cohort685. Compatible Main/Phone/Pico and Apple source variants.
Prerequisites: matching protected-storage/redaction and account-auth-context
chain plus direct token-import caller. Main contextfa3abe7fd0ac329f0f3392b4237eb0cf3e196ad3,
token import7d2b3921cd5e6acf2ff1348ca66257f7ef10f639; Apple context
f236051044833b1186a192ee0fc978538acb6358, token import
e55c62b7ecf33352e8188e1defd0f043298eef07. The corresponding reentrancy guards
must remain present. Import only the matching variant's narrow delta, not an
entire Main AccountManager over Apple provider-specific behavior.

The actual persistAccountToFile failure path now advances _credentialContext and
clears _isWaitingForTokenRefresh before clearing account info and emitting the
existing authRequired signal. Failed read or failed protected write cannot leave
the old transaction eligible for subsequent save-login/profile/preference actions.
No public method signature, successful I/O path, native-store API or signal
vocabulary changed. A new explicit login can succeed under the new generation;
this is not a permanent account-disable flag or a native-storage success claim.

Focused real-Qt test compiles complete ORIGINAL persistAccountToFile,
setAccessTokens and Application::forceLoginWithTokens bodies. Protected-storage
I/O, data representation, profile and preference endpoints are declared test
boundaries. Read failure and write failure must invalidate before authRequired,
reset pending refresh/account state, and stop downstream successful-login writes.
Positive persistence, successful recovery, reentrant replacement login and owner
destruction at authRequired are covered without rewriting production bodies.
Old source reproduces a live old credential ticket at authRequired (RED).

Pending: loginComplete is still emitted before persistence and already-connected
listeners may have started work; this slice does not undo them or redefine the
full login UI outcome. Native store durability/atomicity, read/write callbacks
reentering during I/O, saveLoginStatus failure reporting, same-context latest
request ordering, request origin/HTTPS policy, full foreground/native/artifact
acceptance and physical retention evidence remain separate required work.
Existing scoped replies observe invalidation via their established mechanism;
no synchronous OS/network-stop deadline is claimed. No frozen build SHA is
changed or credited with this later source contract.
