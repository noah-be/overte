# iOS native web adapters

## Original contained text adapter (IO-009)

Consumes General `sh007-native-web/v001`, manifest
`1e4e87fe6e5d29315b02ec934e38e8b28547c2c45ecd4bcfe2eb0ee45d174d7d`.
`NativeWebAdapter` uses the original process-wide `NativeWebPolicy`; it does not
implement a second URL parser or session. The actual Overte target directly links
the adapter and queued Qt startup registration in `ContainedWebView.mm`.

The original API remains explicitly confirmed, HTTPS same-origin **plain text only**.
HTML, XHTML, SVG and PDF responses are denied before response commit. This is a
fail-closed limitation, not approval of a new product mode or full web parity.
The separate HTML endpoint below has its own Shared session contract.
CSS hiding is defense in depth, not an input/autofill security boundary.

The optional view requires an iOS 18.4+ SDK and runtime for the public file-panel
denial delegate; older systems return unavailable without changing the app floor.
Multiple active key windows also return unavailable: the published request has
no originating scene identity, so an arbitrary confirmation target is unsafe.
Only main-frame navigation is admitted; subframes cannot expand this text mode.
The origin confirmation precedes native view creation and loading. Navigation,
redirect, response, history and reload check the current original Shared ticket.
There is no JavaScript, script injection, bridge, shared account-cookie injection,
supplied TLS credential, HTTP authentication, download or external browser fallback.
The data store is nonpersistent. One constant content-rule compilation is shared;
it contains no site grant or private URL and never queues request closures.

Replacement, close, scene/key-window loss and suspension invalidate the ticket
before teardown. A 30-second preparation/navigation deadline fails visibly. A
failed native teardown denies future presentations in this process; it is not
reported as successful OS cleanup. Errors use only the existing redacted event.

Focused host checks:

- `python3 ios/tests/native-web-adapter-test.py` executes the actual C++ adapter
  and original Shared singleton using real Qt; only UIKit operations are faked.
- `python3 ios/tests/native-web-wiring-test.py` checks source wiring and constant
  rule structure. It is not Objective-C++ compilation or WebKit behavior proof.
- `python3 libraries/qml/contracts/test_native_web.py` exercises General's policy
  and the retained original text-only QML component.

Pending: Apple SDK compilation/API availability; real confirmation/VoiceOver and
full-screen/window transitions on iPad and iPhone; no-prefetch before confirmation;
TLS/redirect/MIME-sniffing/autofill/cookie/cache/third-party traffic adversarial
checks; OS teardown and deadlines; full client composition. No simulator/device,
network capture, signing, supported HTML mode or node acceptance is claimed.

## HTML Tablet and world endpoint

`IOSWebView` is registered as `Overte.iOS 1.0` by iOS-owned Qt startup wiring
and selected by `controls/+ios/EmbeddedWebBackend.qml`. The iOS
`FlickableWebViewCore` delegates to the parent native core; the old explicit
text-only component remains `controls/+ios/ContainedTextWebViewCore.qml`.
The HTML endpoint uses the parent-owned
`EmbeddedWebSession`, independently of the original text adapter. The parent
QML wrapper supplies the source identity and forwards each EventBridge direction
once. Configuration is applied before URL assignment.

Tablet pages open an actual full-screen `WKWebView` with native Back, Forward,
Reload and Close controls. JavaScript, forms, user-selected files, HTTP(S)
navigation and user-initiated inline media run in that view. The default
OS-mediated chooser retains the app's iOS 17 floor. Camera, microphone and
motion permission are denied separately; the application's voice permission is
not a website capture grant. Downloads and automatic popup windows are denied;
ordinary target-blank links open in the current isolated view. TLS uses system
verification. No application credentials, account objects, supplied trust,
HTTP-auth credentials or persistent account cookies are added. The data store
is nonpersistent. The full-client bundle templates use the
[WebKit-only ATS exception](https://developer.apple.com/documentation/bundleresources/information-property-list/nsapptransportsecurity/nsallowsarbitraryloadsinwebcontent)
for HTTP browsing while retaining the existing local-network grant and normal
URLSession transport protection. Native HTML input remains subject to normal OS behavior;
this mode does not promise blanket denial of password suggestions or autofill.

World pages paint bounded WK snapshots into the existing Qt offscreen surface.
The open moving-video boundary and the exact artifact-bound physical comparison
are documented in [world video acceptance](WORLD_VIDEO_ACCEPTANCE.md).
Pointer events select DOM elements, normal text input uses Qt's input method,
and wheel events scroll the page. `openNative()` presents the same page for
trusted touch, media controls and system UI. Synthetic DOM input and snapshot
textures do not guarantee arbitrary video, authenticated applications, drag and
drop, file controls or every JavaScript framework. The native route remains
available if capture fails; no fabricated frame is reported.

The page bridge uses the actual Qt WebChannel server, qwebchannel.js and shipped
`createGlobalEventBridge.js`, supplied through `eventBridgeJavaScriptToInject`.
Only the isolated page EventBridge is exported. Every WK message checks the
Shared source generation, native document nonce, current main-frame URL and
64 KiB bound before Qt dispatch. Navigation gets a fresh native document epoch
without expanding the original source origin grant. Reload, redirect, foreign
navigation then Back, source replacement and background/foreground restoration
cannot reuse an old document identity. Fragment-only links retain their current
document. A cached Back document with an obsolete transport identity reloads
its current history item once; repeated failure stops visibly, and an obsolete
verification callback cannot trigger a replacement reload. Outgoing events, DOM input and actual
`runJavaScript` completion callbacks are also guarded against replacement.
A real init/idle exchange exposes `bridgeAvailable`; foreign documents have
normal browsing without EventBridge authority.

Packaged HTML and injected scripts are admitted only under roots derived from
native `PathUtils`, application resources or specific qrc subtrees. File HTML
uses `loadFileURL:allowingReadAccessToURL:` with that approved root. A bounded
native scheme handler maps approved qrc resources, without arbitrary filesystem
access. Explicit source-assigned HTTP(S) scripts are bounded to 1 MiB; script
fetch redirects currently fail visibly. HTML navigation redirects remain usable.
Preparation and loading have a 30-second deadline.

`WKWebSnapshot` captures no faster than once per 100 ms, caps images at 2048
pixels per edge and keeps one native operation in flight across replacements.
It rejects stale, inactive-window and late images, and converts Retina captures
into bounded logical-size RGBA frames. A replacement can wait for the previous
operation under its original two-second deadline.

Focused host checks:

- `python3 ios/tests/embedded-web-surface-state-test.py`: production capture state.
- `python3 ios/tests/ios-web-document-epoch-test.py`: production native epoch with
  the actual parent Shared policy, including reload/redirect races, fragment
  navigation and bounded cached Back recovery.
- `python3 ios/tests/ios-web-channel-test.py`: actual Qt WebChannel server and
  actual shipped JavaScript in Node, both event directions, handshake, origin,
  size and synchronous-close regression. Requires Qt6WebChannel development files.
- `python3 ios/tests/ios-web-selected-qml-test.py`: actual production selector and
  transitive HTML/graphics/Create/audio QML graph, substituting only native module registration.
- `python3 ios/tests/native-web-wiring-test.py`: native target, ARC and startup
  source guards; this does not execute UIKit/WebKit.

The document test always compiles the in-tree parent-owned Shared policy.
The optional `OVERTE_TEST_QT_WEBCHANNEL_INCLUDE` accepts matching extracted Qt
headers when the host has the real runtime library but no development package.
Neither option replaces the production Shared contract or native runtime.

Parent policy/portable QML now reach this branch through direct Apple merges.
Actual Qt6 selector compilation passes the complete web entry graph, retained
graphics Base, Native Create, and the 27 Tablet/settings entries in both default
and iOS profiles. The selected graphics Loader normalizes the fixed base resource
URL because QML type imports may retain either logical or physical selector paths.

Pending integration evidence: Apple SDK Objective-C++ compilation, real iPad/iPhone
presentation and dismissal, WK document-start injection timing, capture
orientation/compositing, trusted forms/media/file selection, system keyboard,
scene transitions and network/privacy boundaries. Host checks do not establish
physical-device parity or certify arbitrary browser applications.
