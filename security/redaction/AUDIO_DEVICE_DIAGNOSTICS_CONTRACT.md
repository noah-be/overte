# AudioClient device-name debug sinks

PX-16 / SH-006, cohort #685. Prerequisite px16-redaction/v001
6f11d1bedf620b39a0c05d93e27fed64b85b1208, manifest
203f5a8498989f40f5f2760282960ed78b16b62d4e624d618de601a34688c52b,
providing the exact existing SafeDiagnostics header. No new sanitizer/API.

Ten actual AudioClient qCDebug statements no longer evaluate deviceName,
default-device name, Windows wave-device names or HMD device identifiers. They
emit only the existing OVT_REDACTED code. These are default-device fallback,
changeDevice forwarding, three Windows debug statements, null-device switch,
input/output switch entry and available-device messages. Their guards, selection,
locks, callbacks and routing statements are unchanged. Device names needed for
actual matching, UI or device selection remain in their legitimate paths.

This deliberately narrow slice does NOT close the separate Android qInfo capture,
watchdog/restart/device traces, codec/pointer/statistics logs, platform OS sinks,
retained outputs or full audio privacy. Do not use ten closed debug expressions
as full PX-16/SH-006 evidence, actual capture/mute/route success or device proof.

The focused test checks every original qCDebug(audioclient) source statement for
the identified device-name expressions, including retained Windows guards, and
executes the ten complete changed expressions using real Qt logging. An explicit
raw canary first proves the Qt sink is enabled. The boundary contains no OS/device
getter, so the closed source expressions cannot inspect such private values.
This is source-expression/Qt-sink evidence, not a full AudioClient/native build.
The old source fails on all ten raw device-name expressions.

Import only the matching Main or Apple four-file release. Apple retains its
native audio shim/guard differences; Main retains its Pico capture policy. No
platform-owner native source is edited. This later source is not qualified by
the separate frozen cold-build artifact. Paused owners consume only on resumption.
