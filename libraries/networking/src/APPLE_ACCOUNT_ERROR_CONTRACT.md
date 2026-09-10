# Apple Account error callback ownership

SH-005 / PX-16, cohort #685. Source implementation only.

Prerequisite: sh005-apple-account-auth-context/v001 at
f236051044833b1186a192ee0fc978538acb6358, with its original completion v003,
deadline, RequestCancellation and protected-store/redaction prerequisites.
This retained Apple callback does not exist on Main; do not add it there.

`requestAccessTokenError` uses the original QObject sender and RequestTicket.
Missing/wrong sender, invalidated context and already consumed finished callbacks
return without diagnostics or UI effects. A current error emits only the existing
closed diagnostic. The complete `requestAccessTokenFinished` remains the single
owner of validation, login failure/success and deferred reply deletion. Thus
errorOccurred followed by finished cannot produce a second login-failure signal.
No raw error, URL, credential or private request identifier is exported.

The pre-existing connections for provider/auth-code requests remain unchanged;
the password path already uses finished only. Refresh retains its distinct
noninteractive behavior. A provider reply which never finishes remains covered
by the existing reply-owned 15-second abort/cleanup policy, subject to Qt event
loop scheduling; this change does not manufacture a finished event or guarantee
hard OS cancellation.

Migration: import the six-file delta on the pinned Apple stack. The original
completion test now executes BOTH complete production methods with actual Qt
signals and tests absent sender, current and stale errors, duplicate errors,
error-then-finished, repeated finished and error-after-finished. Existing malformed
responses, success, refresh, bounds and deletion checks are retained. The original
54-sink diagnostic fixture now uses a real QNetworkReply/QObject boundary to test
the complete guarded method; all closed-expression and state assertions remain.
Transport, account storage and profile operations remain explicit test boundaries.

Remaining: same-context request ordering, reentrant loginComplete receiver
effects, full foreground/presentation cancellation, initial origin/HTTPS/token
policy, streaming allocation, native provider/Qt5/Xcode/device and node acceptance.
No artifact from the separate frozen cold build proves this later source delta.
