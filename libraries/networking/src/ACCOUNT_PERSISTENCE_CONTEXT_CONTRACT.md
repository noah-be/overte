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
Version2 additionally runs persistence and its current-owner/context guard BEFORE
loginComplete in both direct token import and network token completion. Read or
write failure therefore emits the existing authRequired outcome without a prior
loginComplete, and cannot start that success signal's observers. On success the
store has reported success before loginComplete; its reentrant listeners remain
guarded before profile/save actions. No public method signature, native-store API
or signal vocabulary changed. A new explicit login can succeed under the new generation;
this is not a permanent account-disable flag or a native-storage success claim.

Focused real-Qt test compiles complete ORIGINAL persistAccountToFile,
setAccessTokens, requestAccessTokenFinished and Application::forceLoginWithTokens
bodies. Protected-storage
I/O, data representation, profile and preference endpoints are declared test
boundaries. Read failure and write failure must invalidate before authRequired,
reset pending refresh/account state, and stop downstream successful-login writes.
Positive persistence must occur before success is observed. Direct and real
network completion cover read/write failure with zero success signals and reply
cleanup. Successful recovery, reentrant replacement login and owner destruction
at authRequired are covered without rewriting production bodies. Old source
reproduces a live ticket at authRequired (v1 RED); v1 additionally reproduces
success emission before confirmed I/O (v2 RED). Original context/direct-import
fixtures now assert the new intentional persistence-before-success sequence,
retaining invalidation/destruction and no-following-action assertions.

Pending: a successful loginComplete observer may invalidate the context after a
confirmed store operation; already committed storage is not rolled back by this
guard. Logout retains its own erase semantics. Native store durability/atomicity, read/write callbacks
reentering during I/O, saveLoginStatus failure reporting, same-context latest
request ordering, request origin/HTTPS policy, full foreground/native/artifact
acceptance and physical retention evidence remain separate required work.
Existing scoped replies observe invalidation via their established mechanism;
no synchronous OS/network-stop deadline is claimed. No frozen build SHA is
changed or credited with this later source contract.
