# Pico 4 Web entities

## Root cause

Desktop Web entities are rendered by Qt WebEngine. `Web3DSurface.qml` selects
`qml/+webengine/controlsUit/ProxyWebView.qml`; the renderer owns an
`OffscreenQmlSurface` and uploads its texture to the entity quad. The Pico Qt 5
Android Conan profile builds with `qt*:qtwebengine=False`. Qt WebEngine is not
available for this Android target, and `android/cmake-pico-bootstrap.cmake`
provides only empty compatibility targets and headers so shared Interface code
can link. They are not a browser implementation.

Pico also uses the `android_picoInterface` QML file selector. Before this
change no Pico-specific `Web3DSurface.qml` existed, so it fell back to the
generic surface and `controlsUit/ProxyWebView.qml`, whose complete implementation
is the text `This feature is not supported`.

The existing Android `WebViewFragment` is a two-dimensional Activity fragment.
It cannot supply a texture to `WebEntityRenderer`. `clickWeb.js` likewise maps
screen touches to a ray and opens the hit URL; it neither renders nor operates
a world Web entity. Tablet, HUD, and other QML surfaces use separate offscreen
QML paths and are not replaced by this implementation.

## Pico implementation

`qml/+android_picoInterface/Web3DSurface.qml` supplies the Android WebView
surface only for Pico. HTML content is hosted by `PicoWebViewItem`, a
`QQuickItem` registered as `Overte.Pico/PicoWebView`. Its Java peer,
`OffscreenWebView`, creates an Android system WebView on the Android UI thread,
draws it into a bitmap at 10 Hz, and passes ARGB frames through JNI. A QML
image provider and Canvas copy those frames into the existing
`OffscreenQmlSurface`; therefore the
normal `WebEntityRenderer`, entity texture, spatial hit conversion, and
`webSurfaceLaserInput.js` paths remain shared.

Frame readiness is based on receiving a valid image, not on the alpha value of
an arbitrary pixel. This is important for transparent Web content and pages
whose centre is intentionally empty. The JNI receiver also verifies positive
dimensions, multiplication bounds, and direct-buffer capacity before copying a
frame into `QImage`.

Qt hover, mouse press/move/release, and wheel events are translated to Android
mouse-hover, touch, and generic scroll events. A Web entity remains explicitly
non-grabbable in the acceptance fixture, and no near-grab, far-grab, teleport,
or controller-ray thresholds were changed.

Android touch events in one gesture retain the original down timestamp through
move, release, or cancellation. Losing Qt's mouse grab and destroying a page
cancel an active gesture, so the WebView cannot retain a pressed DOM target.
Repeated Down events cancel the preceding gesture first, while Move, Up, or
Cancel without an active Down are discarded at the Java boundary.
Navigating the same surface also cancels an active touch and clears fractional
scroll accumulation before loading the next document. The entity's
`useBackground` value now selects an opaque white or transparent Android
WebView background, matching the shared renderer's transparency contract.
Destroying the Pico Qt Activity bulk-destroys all registered offscreen WebViews
on Android's UI thread so an Activity recreation cannot retain old Contexts,
render callbacks, or page state.
Creation also fails locally with an error log when no live Activity or usable
Android WebView provider exists, instead of terminating the Android main thread.

No Qt WebEngine library, Chromium resource bundle, Gradle browser dependency,
or APK packaging rule is added. Rendering uses the WebView implementation
already supplied by Pico OS. This keeps APK growth to the small Java/C++ bridge
instead of packaging another browser engine.

To bound memory, the captured WebView texture has a maximum edge of 2048 pixels
while retaining its aspect ratio. Pointer coordinates are scaled to that
capture size. At the cap, a 4:3 surface consumes about 12 MiB for each ARGB
copy; the Java bitmap, direct transfer buffer, and native image therefore use
about 36 MiB in addition to WebView/process overhead. The 10 Hz capture rate
limits CPU uploads, but animated pages are intentionally less fluid than a
desktop WebEngine surface. Each active page also adds WebView renderer memory
and GPU texture bandwidth. Sites with video, WebGL, or heavy animation may
reduce frame rate and are not a Pico performance target.

On the A8110 debug build, the local 1007 x 755 acceptance page sustained
71--72 FPS after warm-up, with reported GPU frame times around 11.7--11.9 ms.
One whole-process `dumpsys meminfo` sample reported about 1.92 GiB total PSS,
including about 801 MiB native heap and 476 MiB graphics memory. These are
whole Interface-process observations in the test world, not an isolated
WebView memory delta.

## Local acceptance panel

The interaction fixture station and this optional Web test are separate. Run
`developer/tests/picoWebEntityTest.js` explicitly when Web diagnostics are
needed. After a short pose-settling delay, the script creates one local,
non-grabbable, dependency-free `data:text/html` Web entity centered 2.2 m in
front of the settled HMD camera pose. It contains a
CSS hover target, a click counter, a range slider, and a scroll goal, and deletes the entity when the
script ends. The test script does not move the avatar after startup.

Test both hands separately:

1. Verify the page replaces the unsupported message and is legible.
2. Verify half-trigger displays the spatial ray without pressing the page.
3. Near the existing 90 percent threshold, verify one press and one release,
   and that the click counter increments once.
4. Verify hover, slider drag/release, and vertical scrolling.
5. Move the ray away during and after interaction and verify no hover, press,
   drag, or laser remains stuck.
6. Re-test both grab cubes, the non-grabbable cube, and tablet/HUD input.

## Known limitations

- Android WebView is not API-compatible with Qt WebEngine. The current bridge
  does not implement WebChannel/script-event injection for `scriptURL` or
  `emitScriptEvent`; ordinary DOM interaction is supported.
- Capture is software-rendered and capped at 10 Hz/2048 pixels. Video and WebGL
  behavior is not guaranteed.
- Android WebView security and URL support follow the WebView version installed
  on Pico OS. Local `data:` content and normal HTTP(S) pages are supported;
  external-network behavior was not needed by the acceptance panel.
- Physical controller acceptance still requires observing the headset while
  operating each controller; ADB can prove page creation, frame delivery,
  stability, and captured headset output but cannot synthesize OpenXR hand
  input faithfully.

## Device-free regression

Run `python3 android/tests/pico-webview-bridge-test.py` to verify transparent
frame readiness, JNI direct-buffer validation, Qt action translation,
background forwarding, and navigation cleanup. Run
`android/tests/pico-webview-input-test.sh` for the pure-Java Android gesture
state regression without an SDK or device.
