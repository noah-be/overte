# Pico 4 hardware-independent test suite

For the repository-wide runner that includes this suite, see
[`tests/PROJECT_TESTING.md`](../../../../tests/PROJECT_TESTING.md).

The Pico 4 suite protects Android packaging, OpenXR, WebView, audio, controller
interaction, tablet/Create UI, serverless worlds, performance tooling, and the
headset automation scripts without requiring an Android SDK, emulator, or
headset.

The native Emote app has a registered JavaScript regression and a separate
real-QML pointer test. See [Pico client apps](pico-client-apps.md) for their
commands and the corresponding headset acceptance steps.

## Quick start

Run the complete suite from the repository root:

```bash
android/vr/pico/tests/pico-device-free-test.sh
```

The standard run requires Python 3, Bash, Node.js, a JDK (`java` and `javac`),
and `jq`. See everything the runner knows about or run a focused subset:

```bash
android/vr/pico/tests/pico-device-free-test.sh --list
android/vr/pico/tests/pico-device-free-test.sh --category openxr --category audio
android/vr/pico/tests/pico-device-free-test.sh --test webview-bridge
```

CI can keep running after failures and publish a JUnit report:

```bash
android/vr/pico/tests/pico-device-free-test.sh \
  --timeout 120 --junit build/test-results/pico4-device-free.xml
```

Use `--fail-fast` for local diagnosis. `--skip-missing` is intended only for
constrained developer machines; CI deliberately treats missing tools as a
failure so that lost coverage is visible.

## Coverage model

[`pico4-coverage.json`](../tests/pico4-coverage.json) is a risk-based capability
matrix. Every Pico capability has at least two checks, every catalogued test is
mapped, and critical OpenXR, input, microphone, and world-loading capabilities
are checked independently. `pico4-coverage-test.py` enforces those invariants.

This is not native line coverage: much of the production code needs Android,
Qt, JNI, or an OpenXR runtime and cannot be loaded into a generic host process.
The suite therefore combines:

- executable pure Java and JavaScript behavior tests;
- Python source-contract and XML/Gradle packaging tests;
- mock-ADB integration tests for all headset automation scripts;
- fixture schema and power-analysis behavior tests.

The matrix reports 100% *risk-capability mapping*, not 100% executable line
coverage. Real rendering, tracking accuracy, microphone hardware, thermal
behavior, APK installation, and vendor runtime compatibility remain explicit
hardware acceptance concerns.

## Optional native host regression

If a configured desktop CMake test build already exists, run the Pico-relevant
native suites as an additional layer:

```bash
android/vr/pico/tests/pico-host-regression-test.sh --build-dir build-tests
```

This is intentionally separate because configuring the full Qt/Conan build is
far heavier than the deterministic device-free suite.

## Adding coverage

Add a stable test name and category to `TESTS` in `pico4-test-suite.py`, then map
it to one or more capabilities in `pico4-coverage.json`. Prefer behavior tests
for extracted platform-independent logic. Use source contracts only for JNI,
Android, Qt, or OpenXR paths that cannot execute on the host, and assert safety
invariants rather than formatting details.

## Native embedded web JNI host check

Run `python3 android/vr/pico/tests/pico-embedded-web-test.py` for the actual Qt5
Pico-selected world/tablet texture, keyboard and lifecycle checks. To verify the
JNI method ABI against the compiled production Java, additionally run:

```sh
python3 android/vr/pico/tests/pico-embedded-web-test.py --api-only --jni-create \
  --android-jar /absolute/path/to/platforms/android-36/android.jar \
  --webkit-jar /absolute/path/to/androidx-webkit-1.12.1.jar \
  --qt-jar /absolute/path/to/qualified/QtAndroid.jar \
  --core-jar /absolute/path/to/androidx-core-1.1.0.jar
```

The four paths must be existing reviewed SDK artifacts. The test first compiles
the production Pico Activity/Host, shared web runtime and real Qt bindings
against those APIs; only generated APK resources and PermissionsActivity are
excluded. It then calls the production native endpoint through a real host JVM,
checks the distinct bridge and editor bootstrap arguments, and rejects the
previous compiled create ABI. Only Android Handler/Looper scheduling is replaced
at the host boundary; the Android WebView, OS prompts and device lifecycle are
not executed. This check does not build or attest a current Pico APK. Preserve
artifact hashes and original dependency provenance separately.

## Legacy inline HTML lifecycle regression

The retained `data:text/html` world surface continues to use its original Pico
renderer. It now starts dormant and renders only while its own QQuick surface
is visible/enabled and its Activity is resumed. Activity window-focus loss or
gain does not pause/resume rendering; actual pause/destroy suspends it, and
resume admits it again. Input/keyboard focus is a
separate condition. Hide/background retires queued raster and frame epochs,
pauses this view and its DOM audio/video elements, and releases transient input.
Show resumes the existing page without automatically restarting its media.
A replacement Activity retires only the old owner's views. No process-wide
`WebView.pauseTimers()` is used.

```sh
python3 android/vr/pico/tests/device/test_legacy_web_lifecycle.py
python3 android/vr/pico/tests/device/test_legacy_web_qt.py
python3 android/vr/pico/tests/device/test_production_java_compile.py
```

These cases are also mandatory entries in the 39-case Pico device-free catalog.
The Java check executes the original production lifecycle/frame/cleanup methods;
Android scheduling, Canvas, WebView media effects and native publication are
explicit host boundaries. The Qt5 check compiles the whole production item,
loads the real legacy QML and executes the native callbacks through a real JVM.
Its Java peer substitutes Android WebView and supplies synthetic image buffers;
this does not establish browser video pixels, WebAudio behavior or physical
silence. The SDK compilation additionally checks the actual compiled callback
descriptors. Existing producer, APK and device evidence remains source-bound;
none is reassigned to this repair.

The host visibility test covers effective QQuick visibility and Activity
foreground, not the propagation of an entity's `visible` property into the
shared offscreen renderer. That Main-owned producer linkage must be qualified
separately before claiming entity-hide lifecycle acceptance.

## Normal GOTO startup entry

The Pico startup profile loads the existing bundled `system/goto.js` once in
its own engine. The shared app supplies its tablet/toolbar entry and owns its
address-dialog calls and cleanup. Those calls depend on the callable Main-owned
`DialogsManager` scripting API; this startup change does not qualify that API.
PLACES remains available for the normal directory and Home entries.

`node android/vr/pico/tests/pico-emote-test.js` executes both normal/debug startup
and the actual shared GOTO app with explicit tablet/toolbar/dialog API boundary
replacements, including its own button close and cleanup. They do not establish
a real Script-to-Qt dialog call or external-dialog-close cleanup. Those paths
require the shared native QObject/queued-call regression and device observations.
These host checks also do not establish visible HMD controls, physical
controller/keyboard operation, navigation success or installed APK asset bytes.
Those observations remain part of current-artifact acceptance criterion #1144.

## Inline HTML native editor and HMD keyboard

Inline `data:text/html` uses Pico's contained legacy surface. Its public Android
WebView editor APIs report only active/numeric/password metadata; no field text,
selection contents, DOM script transport or EventBridge rights are added.
The state follows the exact surface/document epoch, input owner and increasing
callback revision. Replacement, blur, hide, disabled state and teardown retire
old editor callbacks. Native composition and selection edit limits remain;
controller clicks reacquire this admitted native view after asynchronous setup.

Run the whole production Qt5 native item and selected Pico QML caller:

```sh
python3 android/vr/pico/tests/device/test_legacy_web_qt.py
python3 android/vr/pico/tests/device/test_legacy_web_lifecycle.py
python3 android/vr/pico/tests/device/test_web_input_queue.py
python3 android/vr/pico/tests/device/test_native_web_policy.py
```

The Qt test executes actual C++/moc, JNI, QML signals, keyboard properties/layout,
Unicode/composition transport and rejected stale callbacks. Android provider
metadata and the HMD keyboard renderer are explicit host boundaries. Its
`OVERTE_PICO_EDITOR_ORIGINAL=1` diagnostic reads unchanged original527 sources
and reproduces the missing native-item forwarding assertion; that deliberate
negative run is not a passing product test.

The separate Android API26/35 tests require Java21, pinned Gradle8.13,
Robolectric4.16.1 and the original resolved Android test AAR classes. Use the
normal reviewed wrapper; an existing private offline artifact store can be
selected through its explicit test-only initialization script:

```sh
python3 android/vr/pico/tests/pico-inline-editor-api-test.py \
  --output /absolute/new/private/editor-api-attempt
```

This test executes real EditorInfo/InputConnection APIs, input-type mappings
and unchanged composition/selection. Its controlled WebView provider supplies
focus/editor metadata because Robolectric has no live Chromium DOM provider.
The Java-frame caller test independently checks its actual owner/input/frame
admission, including revocation during metadata observation. Neither boundary
is presented as an observed DOM focus, real controller keyboard or HMD result.

Current-artifact acceptance must tap actual text, number, password and multiline
fields on inline world HTML using the normal controller. Observe keyboard modes,
text/cursor/composition, blur, hide/show and replacement; queued old document
callbacks must not reopen the keyboard or edit a successor field. Repeat
background/resume separately from ordinary window-focus changes. Existing
physical-key editing and unrelated active surfaces must continue working.
The software inline video path and noncooperative WebAudio qualification remain
separate open requirements; this editor change does not qualify either.
