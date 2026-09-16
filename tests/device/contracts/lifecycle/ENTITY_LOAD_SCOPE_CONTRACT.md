# Entity script load attempt identity

The actual ScriptManager loader assigns a fresh identity before emitting status
updates. Reentrant status observers, repeated URLs and unload/reload therefore
cannot revive an earlier request. Cache completion carries that identity across
real Qt queued delivery; the manager accepts only its current, first completion.
Pending contents are keyed by entity and requested script, so two scripts on one
entity no longer overwrite each other. The update drain validates identity again
and consumes it before entering script code. All three unload entry paths cancel
pending identities before invoking unload callbacks. Stop/finished state also
rejects processing, including already swapped-out responses.

The focused host fixture compiles the complete actual load, dispatch, identity,
cancel and drain functions plus the actual three unload entry prefixes up to
script-detail traversal. It uses real QObject queued delivery, shared/weak manager
ownership and a worker thread. ScriptCache, script details/status observers,
ScriptEngines and the final engine callback are explicit seams. It exercises
repeat/duplicate/stale responses, multiple scripts per entity, queued unload,
reentrant status/load and drain/unload, cross-thread cancellation, stop, deny and
expired manager. Removing the actual identity comparison fails the first stale
response assertion. The separate existing consent fixture verifies the actual
client denial code remains connected at both entries.

This is a load-lifetime prerequisite, not informed consent. Client entity code
remains denied; server/agent/test loader behavior gains request scoping. No
physical cache abort, bounded already-entered native callback, full native header
build, source/origin consent UI or allow/decline/revoke acceptance is claimed.
