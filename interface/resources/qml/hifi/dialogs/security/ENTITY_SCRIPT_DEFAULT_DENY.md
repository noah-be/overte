# Client entity-script default-deny fence (SH-005)

The actual ScriptManager load entry and content-available callback deny client
entity scripts before ScriptCache fetch, compilation, evaluation and preload.
Both CLIENT_SCRIPT and ENTITY_CLIENT_SCRIPT contexts deny; immutable constructor
context is the authority, not mutable Script.type. Embedded code, cache/ATP/file
and network URLs cannot bypass the fence. Force-redownload, unsafe environment
flags and historical allowlists cannot enable it. Late callbacks deny again.

This release intentionally has **no grant path**: the required informed-consent
UI and lifetime-safe finite-revoke backend are not bound. Client entity scripts,
including local/avatar entity scripts, are therefore unavailable. Existing
detail observers receive ERROR_LOADING_SCRIPT with the fixed code
ENTITY_SCRIPT_CONSENT_UNAVAILABLE, rather than remaining LOADING. No URL, entity
ID or code appears in the new denial diagnostic. Server/agent/test contexts
retain their existing loader behavior; this is not a general trusted-script ban.

The fence runs on the manager thread using the existing queued shared ownership.
It is not a hot-reload revocation mechanism or a deadline for a previously
running native/VM callback. No UI/native "allow" button may bypass it. Replace
it only with a versioned, source/origin/epoch-bound consent backend plus verified
in-flight cancellation and independent informed user confirmation.

Focused host test compiles the original denial/status functions, enum and the
actual two entry prefixes with real Qt dispatch/locks. The post-fence network/
engine operations and signal receiver are explicit test boundaries; no full
ScriptManager/engine/device compilation or functional allow/revoke acceptance
is claimed. Full entity-script consent functionality remains pending.
