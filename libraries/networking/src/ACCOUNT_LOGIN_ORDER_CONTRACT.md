# Account credential intent ordering

SH-005 / PX-15, implementation cohort #685. Requires matching Main or Apple
account-persistence-context/v002 and all of its exact transitive prerequisites.
Consume AccountManager.cpp AND .h plus corresponding original-method fixtures
together. Public signatures stay unchanged; no new platform caller is required.

Each password, authorization-code, Steam or Oculus login begins a new existing
RequestScope generation before the user-agent callback/POST. A valid direct
token import does the same before installing data. Older login/refresh replies
cannot emit success/failure, persist tokens or begin profile work. Invalid direct
imports retain their existing failure behavior and do not supersede a valid
pending request. Server change/logout still invalidate and clear admission.

Explicit login sets pending admission until its current finished handler, logout,
server change, current reply destruction or valid direct import. Old reply
destruction cannot clear a newer attempt's pending state. Background refresh is denied while login
or refresh is pending. An admitted refresh advances the generation, so retry
after a refresh error cannot revive the earlier refresh's later finished signal.
There is no queued automatic refresh replay on login completion/failure.

QPointer/ticket checks after the actual user-agent and POST boundaries reject
reentrant replacement/destruction. Existing completion guards now also reject
a newer same-endpoint credential intent initiated from outward callbacks.
Original20ms stale-observation/15s deadline timers remain; requested intervals
are not OS-stop guarantees. No claim of cancellation of already entered I/O.

Tests extract complete original logout/server/five POST/direct/finished/error
methods and original RequestScope into real Qt/moc execution, with declared
network/data/store/settings endpoints. All16 provider pairs in both reply orders
retain only newer token/one success/persist/profile; stale refresh/direct import,
failure/recovery, duplicate refresh admission and user-agent/POST replacement/
destruction are exercised. Separate five-owner tests retain every original15s
deadline without substituting quick supersession for the deadline proof.

Pending: native thread/foreground/persistence durability and in-I/O reentrancy,
profile response ownership after startup, token origin/HTTPS/expiry policy,
full cross-view typed recovery/consent, native/artifact and original node gates.
This does not qualify the build owner's different frozen source or whole parity.
