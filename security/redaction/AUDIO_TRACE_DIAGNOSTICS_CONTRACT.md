# Android AudioClient device/path diagnostic operands

Implementation-only PX-16/SH-006 delta. Prerequisite: exact existing
SafeDiagnostics.h from px16-redaction/v001 (source6f11d1bedf620b39a0c05d93e27fed64b85b1208,
manifest203f5a8498989f40f5f2760282960ed78b16b62d4e624d618de601a34688c52b).
The separate px16-audio-device-debug/v001 closes qCDebug statements; this delta
closes eleven qInfo/qWarning device-name and capture-path operands in the
matching Main/Apple AudioClient source variants. No native platform adapter API
or audio policy is changed.

The actual production statements use the closed OVT_REDACTED token instead of
evaluating deviceName(), path or picoMicCapturePath(). Existing PICO_MIC event
markers, severity, conditional guards, counters, state values and stream order
are retained. Device selection, permission policy, watchdog/restart, audio
capture and file handling remain byte-identical outside these eleven operands.
Legitimate UI/routing device names are not removed.

Focused test extracts all eleven complete original stream statements and runs
them with real Qt logging in both ordinary Android and Pico watchdog branches.
Its audio-state/format/statistic inputs are explicit test boundaries. Device
name/path getters are not declared, so a hidden evaluation cannot compile. Raw
info/warning canary positive controls establish that both sinks work. Original
source is RED on all eleven raw operands. This is not a whole AudioClient,
native routing, microphone or runtime lifecycle build/test.

Consumers must not use the replaced diagnostic device/path fields as identity
or file-discovery inputs. Existing Pico microphone mock transcripts still emit
raw names/paths and are not conformance evidence; the paused Pico owner must
review its measurement consumer before acceptance. No owner files are edited.

Pending: actual raw audio file creation/retention/removal and informed diagnostic
capture policy; remaining codec/pointer/statistic sinks and unbounded counter
values; platform OS/crash/export and retained-output privacy; full PX-16/SH-006
acceptance and native artifact verification. This release neither disables raw
capture nor claims its storage is safe. Frozen Cold Build is a different SHA.
