# Script info and same-thread shutdown public diagnostics

v003 additionally closes all three public debugPrint sinks: no manager, source
debugging enabled, and ordinary managed print. Debug severity and the original
internal ScriptManager::print(message) delivery remain unchanged. The complete
production function executes under real Qt logging in eight routes including
native parent traversal, absent parent/source location, and empty arguments.
Engine/context/logger-interface and internal console are explicit fixture seams.
Original baseline fails the public event assertion; corrected Main passes.
This does not sanitize internal console data or the remaining direct runtime,
module-loader, exception and lifecycle diagnostic sites.

v002 adds the actual error, warning and printed-message wrappers. Their public
Qt sinks use the same bounded event while retaining critical/warning/debug
severity. The five-method fixture exercises each wrapper's normal console,
entity and server-fallback routes and asserts original internal arguments.
Baseline of the newly covered wrappers RED1.598s; no console output removed.

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

This does not prove privacy for the internal console, direct script logging
outside these wrappers, all telemetry, native execution or full-node acceptance. Disabled
timeout blocks remain disabled and unmodified. No stop/evaluation/consent/revoke
behavior changes; entity scripts remain fail-closed pending complete consent and
finite safe revocation. Native signal transport/lifetime remains a separate gate.

Consume the complete matching platform source delta on its pinned base and
transitive contract chain. Preserve Apple-specific ScriptManager behavior; do not
replace the entire file with the Main variant.
