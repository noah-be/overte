# Consent source fetch — unsealed integration work

Client entity loads request the strict ScriptCache profile. Ordinary consumers
retain the default profile. In-flight requests and memory entries are keyed by
URL, redirect policy and the unique consent-session identity. A later world or
new grant cannot reuse a previous session’s relative ATP entry or pending request.
Revocation queues removal of that session’s entries and cancels pending consumers;
late completion and retry paths check the invalidated scope. Delivery rechecks
revocation, including synchronous reentrancy. This does not physically abort the
underlying resource request.
Strict requests reject ResourceManager URL substitutions, including a changed URL
returned by resource creation. Failed initial/retry creation drains pending users
with an InvalidURL outcome. Request metadata used after unlocking is copied first.

HTTPResourceRequest honors the existing failOnRedirect flag using manual redirect
handling and a fresh request without the shared HTTP cache. Before reading a
successful response body it rejects redirect attributes, 3xx responses, changed
reply URLs and unexpected cached responses. ATP already handles the base flag in
AssetResourceRequest; its native execution has not been tested here.

Focused host coverage compiles the full ScriptCache implementation and complete
HTTPResourceRequest methods/header against Qt6. Resource creation, networking
transport, statistics and the resource base are explicit seams; no wire request
or native Qt5/platform build was run. Cache tests cover separate concurrent and
cached profiles, joined strict users, retry policy, two-profile invalidation,
normalization mismatch, inline input and failed creation; cross-session cached
and concurrent ATP loads, late revoked completion, missing/inactive scopes and
revocation during normalization. HTTP tests cover request
attributes, ordinary/strict success, redirect status/body rejection, changed URLs,
cache rejection and unchanged partial-range behavior. Compiled mutations mixing
cache profiles or admitting redirect bodies fail their assertions.

The actual entity loader fixture also verifies strict-profile selection and
retention of the approved source spelling. That fixture's consent decision and
resource fetch remainder are seams; separate broker/renderer fixtures cover their
current transitions. This does not establish trusted human intent, full imported
code policy, physical cache abort, finite native cleanup or original39 acceptance.
Working Application source includes Review/Revoke actions, a scoped prompt queue
and renderer installation. The private native decisions and initial lifecycle
bindings are present but full native UI/lifecycle qualification remains open.
This working source has not been built or deployed. Continue this as one unsealed
integration batch before importing to the other General branches.

Callback integration now carries the original consent request through CallbackData,
installed EntityScriptDetails, the active execution environment and captured
include completions. Timer/handler/instance entry and construction recheck the
request; a later grant for the same URL cannot authorize an older captured request.
Native V8 signal connections capture a weak-manager environment dispatcher. The
actual Qt meta-call body invokes callbacks through that dispatcher. Host tests
exercise the real manager environment capture/admission functions and separately
the complete signal meta-call body with real V8/Qt delivery. Signal registration,
full headers and complete constructor/native-platform execution remain outside
those fixtures. Identity-bypass and signal-dispatch-bypass mutations fail.
