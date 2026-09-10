# Crash annotations and backend diagnostics

CrashHandler applies a closed schema before both queued and live annotation
storage. Supported runtime values are program kind, audio-mixer assignment kind,
boolean shutdown/deadlock/Steam/HMD state, Assignment types 0 through 7, and
unsigned 64-bit decimal process-local thread numbers or GPU-memory counters.
These thread numbers remain available for fault attribution. They are not
persistent device fingerprints. Unknown keys and arbitrary identity, URL, path,
plugin or GPU-description text are ignored. A null C-string is handled safely.

Crashpad and Breakpad startup metadata retain source build identity without
requesting a machine fingerprint. Crashpad release metadata uses BuildInfo's
version rather than the configurable transport token. The configured endpoint
and token still reach backend startup; late-change warnings omit their values.
Crashpad path discovery, database and report-deletion logs retain only event text.
Previously produced reports and archives are not rewritten or deleted here.

The host fixture compiles the actual complete CrashHandler header/methods with
Qt/moc and a capture-only backend. The unused SettingHandle include is omitted in
that fixture. Tests exercise pre-start/live delivery, invalid fields, technical
bounds and late configuration. A second fixture compiles actual backend startup
annotation blocks and logging expressions with explicit BuildInfo, fingerprint,
path and backend-value seams. It does not compile or run the native SDK backends.

This boundary does not sanitize arbitrary process memory in native minidumps,
SDK-generated metadata, third-party logs or screenshots. It does not establish
full PX-16 acceptance. Native crash privacy remains an explicit acceptance gap.
