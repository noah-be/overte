# SH-007 native contained-web implementation seam v001

Actual Shared sources: interface/src/NativeWebPolicy.{h,cpp}, two Application
invokables, and the real selected +ios/FlickableWebViewCore.qml. Native adapter
implementation belongs to the iOS owner in ios/web. Do not define a competing
QML facade or instantiate another Session in production.

## Native registration and behavior

Implement overte::web::Adapter with process lifetime; register once using
installNativeWebAdapter(Adapter*) on QGuiApplication's thread after construction
(the existing native startup registration mechanism may be reused). Missing
adapter, replacement registration or wrong-thread calls fail closed. Add the
native source to the real owned iOS CMake target. Shared .cpp is in the existing
Interface source tree and uses Qt Core/Gui only; no QtWebEngine/WebView dependency.

present(const Request&) noexcept receives a private QUrl, canonical HTTPS origin
and exact integer ticket. Copy the Request for asynchronous ownership. Before
ANY load or prefetch, show a native confirmation containing the canonical origin,
an Open action and equally accessible Cancel. No automatic acceptance or saved
permission. The explicit QML button requests this confirmation, not permission
to silently navigate. True means presentation accepted, not load or render PASS.

Initial supported mode: contained, nonpersistent-data-store HTTPS browsing,
same initial canonical origin, port443, JavaScript disabled. No shared login
cookies/credential autofill, HTTP auth challenge, custom scheme, external window,
download, file/content access, JS/event bridge, WebRTC, script injection, popup,
cache bypass or implicit system-browser fallback. Native back/forward/reload
controls may operate only within the same ticket and policy. OAuth/multi-origin
or JS-dependent authentication is unsupported by this mode and must fail visibly;
it does not replace existing Shared account/domain-auth UI or certify that flow.

Native WKNavigationDelegate calls nativeWebMayNavigate(ticket, absoluteUrlString)
before initial navigation and EVERY redirect, history/reload action and response
commit; false cancels. Cancel a new-window/download/challenge explicitly rather
than forwarding elsewhere. Disable content JavaScript in WKWebView configuration
and per-navigation preferences. Confirm presentation context is the current
foreground scene; absent window/scene/binding or native failure returns false.

dismiss(ticket) noexcept stops loading, cancels pending confirmation/navigation,
clears delegates and releases the associated native view/context. It must not
close another ticket. Shared invalidates the ticket BEFORE calling dismiss, so
late callbacks cannot reauthorize navigation. A failed OS dismissal must remain
an explicit native failure; no finite OS-stop/present receipt is fabricated.
Native user close/cancel calls closeNativeWeb(ticket). Use main-thread callbacks;
global functions invoked from another thread reject without touching state.

## Shared production behavior

The selected iOS QML component no longer creates QtWebView or navigates on URL
assignment. It exposes a visible inline-unsupported explanation and explicit
Open native web view action through ApplicationInterface. Hidden/disabled or
userScriptUrl-bearing views cannot open; URL change, hiding, disable, destruction
and stopUnfocus cancel their OWN ticket. Old view destruction cannot cancel a
newer ticket. QML never fakes history/load success or executes runJavaScript.
No inline WKWebView pixels or scene composition are claimed.

HTTPS input is strict and bounded8192characters; no whitespace/control/backslash,
invalid encoding, userinfo, relative/custom/non-HTTPS URL or non443port. Origin
comparison uses real Qt canonical URL parsing. Tickets remain exact in QML's
number range. Replacement, suspension and close invalidate old callbacks;
resuming never reopens. Native callback reentry cannot open another request.
URLs/origins stay runtime/UI-only and are never diagnostic/result fields.

## Focused proof and limits

Two tests PASS on real host Qt6.11.2: original C++ Session/URL code compiles and
executes positive/malicious URL, origin/port/userinfo, stale/replacement, suspend,
native-failure/reentry/late-callback and thread negatives. Original production QML
instantiates using the real QQmlEngine; only its Application/native boundary is
test-only. URL assignment makes zero open calls, explicit open works, hide closes,
and hidden/injected-script requests fail. Application source caller is checked.
No WKWebView, device, simulator, login, network or full native build was exercised.

This is an importable functional native factory/policy/caller handoff, not SH007
or IO009 PASS. Native iOS registration/presentation/delegate enforcement must be
implemented and focused-tested by its owner. Full renderer/inline-web support,
JITless entity script corpus, simulator/native/hardware and dependency acceptance
remain pending. Keep older sh007-ios-qml/v001 producer limitations separate.
