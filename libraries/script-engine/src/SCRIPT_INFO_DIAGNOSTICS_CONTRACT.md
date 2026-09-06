# Script info and same-thread shutdown public diagnostics

Two public Qt sinks now emit the existing bounded Redacted diagnostic event:
the same-thread waitTillDoneRunning warning and scriptInfoMessage's qCInfo.
The actual wrapper no longer formats script filename or message for public logs.
Its internal infoMessage/infoEntityMessage routes and original message, filename,
line, entity and server arguments are unchanged. Actual consumers include
Application's ScriptEngines connection and JSConsole::handleInfo.

The focused test compiles both complete production methods with real Qt logging
and explicit thread/engine/signal boundaries. It executes same-thread shutdown,
already-stopped worker shutdown, ordinary info messages, entity and server
fallback routing. Public canaries are rejected while original internal console
contents remain asserted. Baseline with actual wrapper was RED1.597s; corrected
Main PASS1.440s. The earlier diagnostic conflated public and console sinks and
is superseded by this more precise two-method test.

This does not prove privacy for the internal console, other script warning/error/
print sinks, all telemetry, native execution or full-node acceptance. Disabled
timeout blocks remain disabled and unmodified. No stop/evaluation/consent/revoke
behavior changes; entity scripts remain fail-closed pending complete consent and
finite safe revocation. Native signal transport/lifetime remains a separate gate.

Consume the complete matching platform source delta on its pinned base and
transitive contract chain. Preserve Apple-specific ScriptManager behavior; do not
replace the entire file with the Main variant.
