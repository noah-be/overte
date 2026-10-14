<!-- Copyright 2026 Overte contributors. SPDX-License-Identifier: Apache-2.0 -->
# Common Android embedded HTML runtime

This Android parent module provides `Overte.Android 1.0 / NativeWebView` and the
`+android/EmbeddedWebBackend.qml` adapter. Phone and Pico hosts can present the
same HTML, JavaScript and Overte EventBridge without copying native code between
product branches. It consumes the parent-owned `EmbeddedWebPolicy.h` contract.

## Product integration

1. Propagate the shared policy and generic `EmbeddedWebView.qml` callers from
   `main` through `android-main` before applying product integration.
2. Include `target.cmake` and call `overte_target_embedded_web(<interface target>)`.
   The helper supplies sources, resources and Qt Quick/WebChannel/Network links;
   startup registers the QML type. The interface resource generator includes the
   Android selector adapter automatically.
3. Set Gradle `ext.overteEmbeddedWebRoot` to this directory and apply
   `target.gradle`. Keep `android.useAndroidX=true` and compileSdk at least 34.
   The adapter pins AndroidX WebKit **1.12.1**. The official Google Maven AAR
   SHA-256 is `18a0a51ad129e0c8563f031d46c8a7e61169f56ae84e562a0d75686941262111`.
   Phone's F-Droid source closure, lock and offline dependency store must include
   this dependency and its transitive artifacts before a qualified Phone build.
4. Implement `EmbeddedWebHost` in the product, call `initialize(host)` on the
   Android UI thread after native-library loading, forward actual foreground
   transitions with `setForeground`, and call `detach` when its Activity ends.
   The host owns Activity identity, screen coordinates, UI attachment/removal,
   explicit OS file/browser choosers and closed diagnostic status identifiers.
   `statusChanged` must show nonzero status visibly outside the native content;
   bridge-unavailable status requires an Android System WebView update action.
5. Native startup supplies only reviewed application resource/script directories
   with `NativeWebViewItem::setPackagedResourceRoots`. No QML property supplies a
   local root. `sourceIdentity` must identify the owning tablet or entity.

The adapter exposes URL/script URL, user agent, background, source identity,
`tablet`/`world-entity` surface, current URL, loading, history, bridge availability,
errors, navigation, JS execution and EventBridge events. Generic callers connect
one event pair. Native code consumes the existing `eventBridgeJavaScriptToInject`
context bootstrap when no explicit bootstrap is supplied; it does not connect
context bridge events itself.

## Presentation and permissions

Tablet uses a **native WebView overlay inside the application**. The product
must map the offscreen QML rectangle into its actual screen, clip to the tablet
content rectangle, preserve other UI and back navigation, and remove the view
when dismissed. This path preserves browser media rendering, user gestures and
native DOM keyboard/composition. External OS browser opening is a separate
explicit user command and does not qualify embedded-tablet acceptance.

World entities and texture tablets attach a hardware WebView to an app-owned,
private `OWN_CONTENT_ONLY` VirtualDisplay and a non-focusable Presentation. The
SurfaceTexture is consumed on an EGL handler, sampled into a bounded FBO and
read back at most about every 100 ms (maximum 2048 pixels per edge). This follows
[Chromium's supported snapshot path](https://chromium.googlesource.com/chromium/src/+/refs/tags/141.0.7360.13/android_webview/docs/software_draw_deprecated.md):
software Canvas snapshots omit video/WebGL. Phone's visible native tablet overlay
continues to render directly in its Activity.

Every asynchronous frame retains its original source/page/document/surface
lease. A WebView visual-state callback drains previous buffers, requests the
next hardware draw and requires a newer SurfaceTexture timestamp. Resize,
navigation, pause, hidden state, replacement and destruction invalidate old
visual/readback callbacks. VirtualDisplay output stops while suspended. Resizing
recreates the Presentation window (Android cancels windows whose display metrics
changed) while retaining the document. GL resources belong to one handler; its
context/surface are released without terminating Qt's shared EGL display.
Readback explicitly flips GL rows and packs RGBA into premultiplied BGRA for Qt.

SDK/API compilation, real frame-lease race tests and actual Qt scene graph pixel
checks qualify source/host behavior only. User-driven original MP4 moving pixels,
audio, exact provider/codec behavior, transparent pages, multiple surfaces and
thermal/resource budgets still require tests on the actual Phone/Pico artifacts.

HTTP(S) navigation excludes embedded credentials and privileged schemes. Known
packaged resources map to a reserved HTTPS origin and a nonreused surface handle;
canonical paths, traversal and symlinks are checked against the native root.
File/content navigation and universal filesystem access remain disabled. Only a
visible tablet may request a product-owned OS file chooser after explicit user
selection. Browser microphone, camera and geolocation requests are denied;
Overte's existing native voice is independent. Browser audio/video requires a
user gesture, and hiding/backgrounding cancels input and pauses media.

## Bridge and text input

Full bridge support requires provider capabilities `WEB_MESSAGE_LISTENER` and
`DOCUMENT_START_SCRIPT`. AndroidX supplies authoritative source origin and frame
metadata. There is no raw JavaScript-interface fallback. Unsupported providers
keep the document usable and report an actionable WebView update message.
Source grants and native document epochs are separate. Every inbound/outbound
message is bound to the active surface/document; bridge traffic is bounded to
64 KiB and only the original origin (or exact packaged document) can access it.
The private Qt channel accepts initialization, idle, its script-event signal
subscription and only `eventBridge.emitWebEvent` invocation; inherited QObject
slots and property mutation are denied.

Texture input reports bounded real DOM surrounding text, cursor/anchor, password
hints and selections. Atomic IME replacement excludes the old preedit range,
supports commit/cancel/preedit cursor and nonlocal replacements, and preserves
UTF-16 codepoints. It dispatches DOM composition/input events and preserves
surrounding rich-text nodes. Exact browser IME behavior, preedit formatting,
undo/redo, custom editors and caret placement need device qualification; these
host tests do not establish Android provider behavior.

Private editor state uses its own AndroidX message listener and document-start
helper, independent of the original document's Overte bridge origin. Ordinary
cross-origin navigation therefore retains texture text input without granting
the new document a Qt WebChannel, EventBridge or owner-script capability. The
private listener's origin wildcard permits future navigation; it does not grant
messages authority. Native code validates the provider-reported main-frame
origin against the current document, active source generation, exact document
epoch, permitted navigation and 64 KiB limit, and repeats lifetime checks before
queued delivery. Subframes, opaque origins, privileged URLs and old document
messages are rejected. Password contents remain in the DOM. IME commands enter
through a separate bounded JSON-object method with fixed editor invocation,
never the owner-authorized arbitrary JavaScript API. Suspension revokes both
transports; the editor bootstrap never installs `qt` or an Overte transport.
Both paths require the same explicit provider features; no raw JavaScript
interface substitutes for authoritative frame metadata. See the official
[AndroidX listener metadata](https://developer.android.com/reference/androidx/webkit/WebViewCompat.WebMessageListener)
and [document-start/origin rules](https://developer.android.com/reference/androidx/webkit/WebViewCompat).

## Verification

Dependency-light registered suite:

```bash
python3 android/common/web/tests/run.py
python3 tests/run-project-tests.py --profile quick --timeout 240
git diff --check
```

Production C++/moc/resource/JNI compilation, real Qt WebChannel interoperability,
QML instantiation and complete Java API compilation:

```bash
python3 android/common/web/tests/run.py --native \
  --qt-root <Qt5-sysroot> --policy-include <parent-policy-directory> \
  --android-jar <SDK-platform-android.jar> --webkit-jar <WebKit-1.12.1-classes.jar>
```

`--policy-include` allows a reviewed owning-parent header before propagation; the
module does not carry a second policy. Provider capability, foreground races,
DOM IME, approved local docs, browser history, EventBridge and user-driven video/
audio must also pass on the exact Phone/Pico application artifact and hardware.

Native overlays receive separate scene bounds and the intersection of QML clip
ancestors. The three-argument Host placement callback must apply that clip along
with the actual platform surface clip; its two-argument compatibility fallback
cannot establish clipping acceptance. Scene rectangles describe bounding boxes,
so arbitrary rotated overlays still need product qualification. Hosts may call
`EmbeddedWebView.relayout(this)` when their native surface dimensions arrive or
change; this retries placement without rebinding a document or source grant.

The selected Android backend supports `presentation: "auto"`, `"texture"`, or
`"native-overlay"`. Auto uses an overlay for tablets and textures for world
entities. A visible texture tablet can invoke the OS file picker only after the
native policy verifies its current Tablet grant, exact page and document. World
entities cannot obtain picker permission by changing presentation.

The private display uses 160 dpi, giving its WebView an explicit density of one;
CSS viewport, hardware output and pointer coordinates therefore agree. Texture
size stays within 2048 pixels per edge with preserved aspect ratio. Pointer
conversion includes the downscale ratio for oversized requested surfaces.
Scrolling uses the attached hardware ViewRoot; no manual Canvas/whole-document
drawing is requested. These host checks do not qualify scrolling/media on a device.
The backend exposes read-only `editorFocused`, `editorNumeric`, `editorPassword`
and `editorFocusChanged(active,numeric,password)` for product keyboard routing.
Focus clears on navigation, hiding, backgrounding and native focus loss. Text
input on foreign documents uses the independent private editor transport without
granting the Overte channel or owner script execution; target IME remains unqualified.

## JNI names in release builds

The Gradle helper applies this module's `proguard-rules.pro` to every build type.
Only the Java entry class called by native JNI is retained by name with its
methods; other implementation classes remain eligible for R8 optimization.
Do not remove these rules when enabling release minification.

`android/common/tests/jni-shrinker-test.py` optionally compiles all three real
Java endpoints against Android SDK/AndroidX artifacts, optimizes them with an
explicit R8 JAR and checks every native lookup and callback descriptor. An
unprotected negative control loses the endpoints. Supply `--r8-jar`,
`--android-jar`, `--webkit-jar`, `--core-jar` and `--annotation-jar`; the JDK is
discovered from `javac`, or set with `--java-home`. JVM classfile output uses the
actual JDK LambdaMetafactory declaration because Android's API stub omits it.
This host check does not qualify the product's AGP release APK or device runtime.

## WebAudio lifecycle

The shared runtime uses the already pinned AndroidX `MUTE_AUDIO` capability per
WebView. The default is muted before the first load. Hide, background,
navigation, source revocation and destruction mute before optional DOM actions
or presentation shutdown. A current visual/document ticket may unmute only the
exact visible foreground instance and Activity. Browser user-gesture policy
remains enabled. This output fence is independent of the Overte bridge grant;
ordinary foreign HTTP(S) pages do not acquire bridge authority.

Inactive lifecycle revisions are distinct from the active-only bridge check.
Queued dispatch checks the exact instance, owner, Activity and raw revision.
Creation callbacks carry their original revision; a changed source or
presentation closes only that obsolete instance. Every new WebView gets a fresh
revision, including explicit reload of a previously closed page.

A provider without reliable native mute can use a visible document. Its first
actual suspend, including navigation away from a running page, closes only that
WebView. The UI explains the lost transient state and provides a pointer,
keyboard and accessibility `Reload page (GET)` action. Returning to visibility
alone never restores it. Only bounded navigation URLs survive; no POST body,
form values, JavaScript objects or running contexts are restored. Such an older
provider does not offer full state-preserving parity. A failed native mute uses
the same local close path. Other WebViews and Overte voice are unaffected.

Native mute prevents audible output; it does not prove that AudioContext,
AudioWorklet or JavaScript execution has terminated. Destruction ends the
fallback document, but exact-artifact provider behavior and acoustic silence
still require device qualification. No global timers, AudioManager stream mute
or shared renderer-process kill is used.

`tests/run.py --native --reproduce-old-hide` executes the actual Qt item,
QML adapter, JVM and JNI into the production lifecycle dispatcher. It also
reproduces the original active-only hide rejection as an expected negative.
Only Android WebView/Looper effects are represented at that boundary. The
portable production-controller tests cover two-page isolation, unsupported and
throwing providers, stale callbacks and bounded URL history. These tests do not
execute Chromium DOM or establish real audio silence.
