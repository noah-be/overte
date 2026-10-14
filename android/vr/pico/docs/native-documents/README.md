# Pico native document import and Snapshot export

Pico links the owning Android `documents` and `snapshot` modules into the full
`interface` library. Their UI/storage dependencies never enter the early
`picoOpenXR` library. Gradle uses the shared Java/resource/keep-rule modules;
the application manifest declares the narrow Snapshot provider and receiver.

`PicoNativeBridges` resolves the actual live Activity class loader and explicitly
registers both modules' actual native initialization/completion descriptors.
Only then does `PicoNativeDocumentHost` admit Android-main-loop initialization.
It supplies an immutable Activity for both shared adapters. Resume plus genuine
window focus and current Activity ownership authorize delivery; pause alone
preserves an intentional system chooser. Destruction revokes the lease. Stale
readiness, queued initialization, results and detach cannot bind a replacement.
A recreated Activity reuses the actual successful binding receipt, since the
running native application need not execute its setup again.

Native document returns precede Web/Qt result handling. Provider documents are
copied by the common adapter into retained app-owned local files before Main's
`FileDialogHelper` returns them to the ordinary Scripts/Assets surfaces.
The shared count/byte/name/filter/ownership checks and script consent remain
in their owners. Unique selected names remain siblings; duplicate names use
separate directories. The additive folder picker retains a complete bounded local hierarchy for the
normal bundle review and batch upload; this does not qualify rendered glTF/OBJ
projects or a real provider journey.
Successful files remain available after the dialog ends.

Snapshot uses the shared native-known storage root and export policy. Save/Share
use the common Android adapter. The provider grants the selected image only;
original captures remain available. A chooser handoff is distinct from a
recipient actually saving a copy.

## Executed host checks

- `python3 android/vr/pico/tests/device/test_pico_native_classloader.py`
  compiles the complete production Pico bridges/host, Main `FileDialogHelper`
  and Android document/Snapshot C++ adapters and moc. An actual foreign-loader
  JVM executes initializer, request and completion calls; real Qt callbacks
  return to their owner thread. The actual tree request passes retained nested
  files through JNI validation and the production helper manifest; owner
  destruction cancels the original request ID and rejects a late completion. It creates the logically selected production
  Snapshot QML with `android_picoInterface` and `android` selectors. It checks
  delayed readiness, duplicate initialization, pause/focus, immutable result
  routing, recreation without repeated application setup, obsolete queued
  initialization, destruction and an actually compiled wrong callback ABI.
  Android Activity, main scheduling and OS/provider effects are explicit fixtures.
- `OVERTE_NATIVE_QT_MAJOR=5` selects the actual Qt5 kit for the same test;
  default is Qt6. Set `OVERTE_QT5_ROOT` for a nonstandard Qt5 SDK.
- `PICO_R8_JAR=/path/to/d8.jar` additionally runs actual R8 classfile optimization
  on the two production Pico readiness declarations with explicit Android
  fixtures and real JDK declarations. Both JNI descriptors survive Pico keep
  rules; the unprotected host disappears. This is not an AGP release APK check.
- `python3 android/vr/pico/tests/device/test_activity_teardown.py` executes the
  original Activity pause/resume/focus/destroy/result methods with explicit OS
  effects, including native-document then Web then Qt result precedence.
- `python3 tests/device/contracts/script_assets/test_script_assets_qml.py`
  and `OVERTE_NATIVE_QT_MAJOR=6` execute the actual selected tablet surfaces,
  production Qt tree/file models and helper with real pointer/keyboard edits,
  permission denial, Scripts operations and Asset operations. Engine/network
  effects and mobile provider selection are documented fixtures.
- `python3 android/vr/pico/tests/pico-embedded-web-test.py --api-only
  --android-jar /path/to/android.jar --webkit-jar /path/to/webkit.jar
  --qt-jar /path/to/QtAndroid.jar --core-jar /path/to/core.jar` compiles production
  Pico Activities/Hosts, actual Qt bindings and all three common Java modules
  against the specified Android/AndroidX artifacts. APK-generated resources and
  `PermissionsActivity` are excluded. Historical Qt artifacts are API checks,
  not qualification of a current product dependency build.
- `python3 tests/run-project-tests.py --profile quick --timeout 240`
  runs the registered shared suites and Pico catalog.

## Remaining product evidence

A source-bound full APK build must establish CMake linking, packaged QML/native
modules, provider/resources and release rules against current reviewed receipts.
The historical September input contract does not bind the current source graph.
No new native APK build, Jenkins/device job or publication is implied here.
Actual Pico provider permissions/copy failures, cancel, pause/return, Activity
recreation, controller/HMD keyboard interaction, genuine image Save/Share and
ordinary script/asset engine/network outcomes still require artifact-bound
hardware acceptance. Native Web video composition remains a separate shared
Android renderer prerequisite; elapsed player time or DOM animation is not
visible moving video evidence.
