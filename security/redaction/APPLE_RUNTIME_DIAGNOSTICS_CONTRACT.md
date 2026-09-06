# PX-16 Apple Shared runtime diagnostic sinks v001

Requires px16-redaction/v001 SafeDiagnostics.h and preserved apple-ios
IOSRuntimeLogging.h/NodeList variant, including px16-nodelist-diagnostics/v001.
Source base d2a22d7c20cc645d7c2cce3f2776922d7522c39b (General's Apple preferences
copy). Preferences code is not an added functional dependency of this delta.
Main/Phone/Pico do not import this Apple-only header or whole Apple source tree.

`logIOSRuntimeEvent(DiagnosticEvent)` sends the same static closed event bytes
to Qt and Apple's public os_log transport. Unknown enum values become Redacted.
The legacy variadic `logIOSRuntimeMarker` discards arguments without formatting
them and emits Redacted. Caller argument expressions may still evaluate before
entry; this is not cancellation or suppression of arbitrary expression effects.
The config-reload call no longer includes path/size/keys/schema. Its actual
configuration values and internal entity-evidence state are not redacted.

NodeList's actual first-connection block no longer logs domain/session IDs
through either the macOS qInfo marker or iOS variadic marker. Both use the same
ConnectionReady diagnostic after the existing state setters. Address lookup,
UUID/local state delivery and single transition behavior are unchanged.

The COMPLETE original Shared header compiles/runs against real host Qt, with
Apple os/log.h transport alone substituted. Both Qt-only and iOS-sink branches
receive raw captures, without the global sanitizer. Canaries, a streaming-side-
effect payload, unknown event, actual file-config reload, internal entity-state
round-trip and COMPLETE original NodeList connection block are exercised. The
NodeList dependency/socket receiver is a test boundary. Existing original
52-expression/username tests and extra-sink guard now both pass on Apple source.

IMPORTANT EVIDENCE MIGRATION: legacy OVERTE_IOS_* / OVERTE_MACOS_* free-text
markers and their identifier joins are no longer emitted by these helpers.
Do not accept a generic Redacted/ConnectionReady event as world/render/present/
session/artifact evidence, relax old assertions or synthesize marker receipts.
Such gates remain unaccepted pending a separately reviewed, generation/source/
artifact-bound structured evidence producer. No native os_log/SDK/Qt5/device
execution is claimed. Other direct OS sinks (including VKBackend/VKPipelineCache),
retained logs/export/crash and original full PX16 acceptance remain pending.
