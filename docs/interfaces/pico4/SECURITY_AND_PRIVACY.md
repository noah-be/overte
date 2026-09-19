# Pico 4 security and privacy

The APK and dependency graph are experimental and require review before use with
valuable accounts. The build and release workflows separate untrusted
device-free checks, trusted builds, signing, and physical device access.

- Keep signing keys and passwords only in the protected release environment.
- The device runner needs the expected certificate fingerprint, not the key.
- Do not expose headset serials, raw logs, microphone captures, account data, or
  complete visited locations in repository artifacts.
- Review microphone, WebView, local content, network endpoints, account/login,
  user-generated content, and store privacy declarations before distribution.
- A store may re-sign an APK; treat those bytes as a different artifact and test
  them again.

Detailed microphone and web-surface behavior is documented in
`android/docs/pico-microphone.md` and `android/docs/pico4-web-entities.md`.

## Original Shared DomainHandler diagnostics

PX-16 contract px16-domain-diagnostics/v001 is consumed unchanged: source
6fac7b9768c59198da6db101e8c3ca501d7c60a1, manifest
36b556dbaf94d21279877330750fc0064fa2628e3f89226ed7e7abc8c70fea45.
Its exact SafeDiagnostics prerequisite is already installed; import follows
sh005-ice-hostname/v001. Pico links the original networking library and uses
NodeList's DomainHandler (see LIFECYCLE.md), with no native override or new hook.

All 30 direct Qt log expressions now emit only the original closed Redacted
event, retaining severity/category but deliberately removing diagnostic detail.
Hostnames, sockets, domain IDs, settings, refusal reasons/extraInfo, counters
and queue sizes do not enter these calls. The URL-prefix-only filter and
diagnostic-only queue inspection are removed. Legitimate settings, reasons,
extraInfo and redirect URLs remain unchanged for application/signal receivers.

One original real Qt test executes every actual log expression and complete
settings/error-redirect methods against a raw unsanitized sink (PASS1.441s).
Synthetic canaries verify closed output without altering legitimate data.
Packet/signal receivers and unchanged policy predicates are test boundaries.
The affected original ICE setter/completion regression passes (1 test, 1.699s).
All five imported source/test files exactly match the release.

This resolves direct DomainHandler logging, not all downstream receivers,
network/third-party/OS sinks or whole-client privacy. Full DomainHandler/platform
compilation, physical privacy canaries, retained artifact inspection and original
PX-16 acceptance remain pending. No real endpoint, device selector or private
runtime log is included in the focused checks or handoff.

## Canonical adapter subprocess errors

sh004-adapter-error-privacy/v001 source 98bb43ffadf019c993f5cc72be23d53abe717f23,
manifest cd65358ce948f76ba2dfb9dcee8f6d7770c31d65f1376a88083b32e7ba6ca5c9,
is imported as the exact narrow patch on existing sh004-results/v003 and its
v001/v002 prerequisites. The two new test/doc files match the release. run.py
differs from its full snapshot only by the pre-existing --fail-fast parser
option, intentionally preserved; the released adapter_call method is unchanged.
No Pico adapter schema, native identity hook or V8 prerequisite is added.

Original discover/describe/cleanup now discard child stderr rather than retain
arbitrary device/tool diagnostics. Nonzero exit, startup/timeout, invalid UTF8
or invalid JSON expose only OVT_TEST_INFRASTRUCTURE_ERROR, with ordinary chained
tracebacks suppressed. Successful JSON and original identity/result/cleanup
validation remain unchanged. Failure is not converted into successful cleanup.

Original real-child privacy tests cover five cases. Pico also executes its real
canonical Android --kind pico --native-binding entry as a child through the
original runner: missing candidate inputs reject before ADB construction and
become the fixed infrastructure error. The existing original runner-to-Pico
producer/consumer test asserts DEVNULL and models discarded stderr accurately;
its native OS/module/signature effects remain synthetic. Original execution
identity/JUnit and harness success/module-failure cleanup checks also pass.

This is a subprocess error boundary, not complete artifact privacy. Stdout is
still captured without a size bound; successful describe JSON, module.log,
module-owned files, screenshots, crash/export collectors and debugger locals
require separate review. No real device, installed artifact, hardware operation,
whole PX16/SH004 privacy or original node acceptance is established here.

## Login credential predecessor diagnostics

px16-login-dialog-diagnostics/v001 source 0030daa788e044fb2fcab00e3e93326efe0ba8b4,
manifest 5aab55d84bee9a286809eb842159d7a67dfc9d5076de9f3649581885059ca8cd,
is consumed unchanged for Main/Phone/Pico; all four files match. Original
SafeDiagnostics and PhoneLoginState.h are present; the latter matches source
hash 3da63a04c1278f75b5aa0cf92fc110e84a64edbf906ee91a8ac6512515931010.
The separate Apple variant is not imported. No domain-auth code prerequisite.

Complete original LoginDialog::login/loginDomain/signup replace their three
username log expressions with the existing fixed Redacted event. Credentials,
signup JSON/callbacks, actual account/domain dispatch and Phone beginRequest
guard are unchanged. This resolves the concrete predecessor username sink
request; the earlier domain-manager diagnostic fix alone did not cover it.

Explicit OVERTE_LOGIN_VARIANT=main original test passes all three define stacks
(1, 11.775s), using actual PhoneLoginState, real Qt JSON and positively probed raw
debug capture. Transport calls and signup route/receivers are test boundaries.
Pico original Setup/domain dialog/DomainHandler/NodeList caller pin passes
(1, 0.019s). Qt SFINAE warnings retained. No duplicate manager/native test rerun.

This does not fix Pico LoginDialog completion/failure forwarding; General has
that separate active source request. Whole QML/native provider/consent and
other sinks/logs/files/screenshots/crash/export remain pending. No whole privacy,
PI/SH/PX acceptance or physical login claim follows from closed diagnostics.
