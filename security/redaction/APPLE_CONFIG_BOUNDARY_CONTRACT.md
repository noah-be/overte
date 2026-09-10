# Apple diagnostic configuration input bound

The actual Shared IOSRuntimeLogging.h hot-reload reader now accepts at most
1 MiB, inclusive, of JSON input. It checks QFileInfo before opening and reads at
most the limit plus one sentinel byte, rejecting errors, excess bytes and an
incomplete read. Oversized input cannot replace the last valid configuration.
Missing files still clear the cache; malformed or partial replacement retains
the last valid object and retries through the existing one-second cadence.
Closed diagnostics, accepted configuration values and the real renderer helper
calls retain their existing semantics. No contents or path are logged.

Requires px16-apple-runtime-diagnostics/v001; source-only Apple Shared delta.
The complete original header test uses real QFile/JSON/cache and real helpers,
including oversized valid JSON, the exact inclusive limit, valid replacement,
malformed replacement, deletion and recovery. No native SDK or renderer run.

This bounds input bytes, not the total allocation cost of JSON object parsing,
string conversion or renderer collections. It does not enforce an approved
diagnostic schema, authorize individual modes, or attest configuration origin.
File replacement races, wall-clock rollback, symlink policy and retained data
remain separate work. This is not structured world/render evidence: the five
legacy evidence-source failures and generation/source/artifact-bound producer
and consumer migration remain pending and must not be relaxed.
