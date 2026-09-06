# Account settings snapshot and request ownership

Additive SH-005/PX-15 source contract. Consume only after the matching
account-reply-cleanup/v001 and its complete transitive prerequisites. Main and
Apple exports are distinct; preserve Apple token-error slots and Qt-versioned
connections. No consumer-owned paths or build inputs are changed.

## Implemented behavior

- AccountSettings snapshots bind payload and revision under the same read lock.
  Writes advance a strictly increasing revision despite clock collisions or
  rollback; revision exhaustion throws before mutation rather than wrapping.
  Conditional server application compares and mutates under one write lock.
  Explicit same-value local intent during Loading or from NotPresent/LoggedOut
  advances the revision too. Unchanged values already Loaded remain a no-op.
  Download admission atomically rejects unacknowledged local changes and captures
  the requested revision/Loading state under the write lock. Rejection schedules
  onward upload instead. Only acknowledgement of the exact current revision
  clears the local-change latch; older successful PUTs cannot clear newer edits.
- PUT admission is single-flight, reserved before reentrant callbacks. A reply
  acknowledges its own sent revision only, once, for its current credential and
  upload request. New local values remain eligible for a later timer/caller PUT.
  Reply destruction releases only its own admission. Redirects are manual,
  responses bounded to 1 MiB and successful error-free 2xx object JSON required.
- GET carries credential, latest-download and requested-local-revision identity.
  Local changes during GET win, including on failed GET: retry stops and the
  upload timer starts for Loaded settings. Capture/loading precedes user-agent
  callbacks. A PUT supersedes old downloads. Retry callbacks require their
  original current credential/download tickets. The existing deadline helper
  and reply cleanup are applied to both request types.
- Logout, account/server replacement, accepted interactive/direct token login
  and persistence failure reset settings state and download/retry metadata.
  Normal token refresh retains settings. Reset does not reopen an outstanding
  upload's admission. Uninitialized LoggedOut/Loading settings cannot be PUT.
  Logout's reentrant final-post and outward continuation are fenced.

## Focused evidence

`test_account_settings_upload.py` compiles original complete production request,
completion, reset and deadline methods with real Qt reply/transport objects;
settings/network creation are explicit fixture boundaries. Its second compile
uses the actual AccountManager header and AccountSettings.cpp. Negatives include
out-of-order/duplicate replies, credential/request replacement, malformed/error/
oversized/timeout-marked responses, callback destruction, and retained local
edits with onward upload admission. The marker test is not a measured deadline.

`test_account_settings_snapshot.py` compiles the actual AccountSettings class and
all methods, with only a deterministic clock seam. It checks 20,000 concurrent
writes/snapshots, conditional apply, Loading/local edits, logout, clock collision,
rollback and exhaustion. Auth-context, completion, direct token and persistence
fixtures cover changed reset boundaries; the actual refresh path preserves data.

Historical REDs proved acknowledgement of an unsent revision, a GET overwriting
a newer local value, Loading blocking a local edit, clock revision collision,
and a retained edit without an active onward upload timer. These are not hidden
by changing error assertions or inventing platform acceptance.

## Acceptance still open

These are source/host Qt tests, not full native clients, device UI, server or
per-node acceptance. Client single-flight does not establish server-side write
ordering after an uncertain timeout/abort. Exhausted GET retries can leave
Loading; retry-exhaustion presentation/recovery remains open. No general cross-thread manager,
total streaming allocation, initial auth-origin/HTTPS, or complete cancellation/
foreground guarantee is made. Platform consumption, build/artifact/runtime
checks and original feature criteria remain independently required.
