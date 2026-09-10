# Client entity-script consent — working integration

Client entity code remains denied by default. The local working source adds
native `Entity Scripts: Review` and `Entity Scripts: Revoke` actions, also reached
from the shared security panel. Review creates a new session and presents queued
source decisions; No is the default. Allowlist settings remain an additional
restriction and cannot grant this consent by themselves.

Requests are bound to the actual renderer manager, entity, source string and
session identity. Renderer and Application recheck a live request before acting.
Closing a session invokes weak-manager stop hooks directly; it does not wait for
a renderer event loop to request VM interruption. Domain/reset/disconnection,
account, background and shutdown paths are being integrated with invalidation.
The displayed source fingerprint identifies the source string, not downloaded
code bytes. Permissions encompass the trusted script and code it loads, as the
prompt states; there is no claim of a general script sandbox.

This is unsealed work in the General Main integration tree. It is not a qualified
platform release or proof of informed human input on native devices. Native
headers/platform rendering, all lifecycle/duplicate-event ordering, physical
resource cancellation and finite already-entered native callback cleanup remain
unaccepted. Strict ScriptCache entries and pending requests now carry a unique
consent-session identity, including domain-relative ATP sources. Focused Qt
fixtures cover session isolation, revocation and Pico redundant domain/reset
branches; actual world mutation and native UI remain explicit seams. The
surrounding 39-node acceptance scope is unchanged.
