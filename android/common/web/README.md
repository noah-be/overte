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

World entities use `QQuickItem` scene graph textures: at most 2048 by 2048 pixels,
updated about every 100 ms. Software bitmap capture is **not proof of HTML video
rendering**. Keep the existing Pico world renderer until the replacement is
qualified. A hardware compositor/texture transport and exact-device media
results remain required for world video parity.

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
