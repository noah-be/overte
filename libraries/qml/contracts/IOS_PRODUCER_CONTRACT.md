# SH-007 actual iOS QML producer inventory and explicit limitations

This inventory describes the existing iOS/Qt6 source stack, not the obsolete
claim that every QML surface still exports an external GL texture. It does NOT
claim simulator, full-graph linkage, world/screen presentation or node PASS.

## Screen and world-QML paths

1. interface/src/Application_Graphics.cpp: initializeGL explicitly requests
   OffscreenSurface::SharedGraphicsContext::Backend::Software. It does not ask
   Qt Quick to render using a native Vulkan/Metal QRhi device.
2. libraries/qml/src/qml/impl/SharedObject.cpp: before constructing the first
   offscreen QQuickWindow on iOS/Qt6, selects QSGRendererInterface::Software.
   initializeRenderControl returns without QRhi initialize on that branch.
3. libraries/qml/src/qml/impl/RenderEventHandler.cpp: skips GL canvas setup,
   installs a QImage paint-device target using fromPaintDevice, calls the
   software render control, publishes through SharedObject::updateImage.
   Dirty-region contents are retained between draws; resize clears the target.
4. SharedObject's bounded latest-image slot is fetched by OffscreenSurface::fetchImage.
   Screen consumer: interface/src/ui/ApplicationOverlay.cpp::updateIOSQmlTexture,
   converts RGBA, creates ordinary gpu::Texture and assigns CPU mip bytes.
   World-QML consumer: libraries/entities-renderer/src/RenderableWebEntityItem.cpp,
   whose iOS branch likewise fetches QImage and uploads ordinary texture bytes.
5. Existing gpu/gpu-vk rendering, VulkanDisplayPlugin and vk swapchain present
   the world/overlay through MoltenVK and CAMetalLayer. Image upload is not proof
   of a completed present or correct pixels. World and screen need exact-head
   simulator observations and the later authorized iPad checkpoint separately.

The selected implementation is SOFTWARE_QML_CPU_UPLOAD_TO_VULKAN, not native-RHI
QML, a GL-sharing bridge, or GPU-accelerated QML. Native WKWebView content is not
proven to be part of these software images. Existing iOS rendering inventory in
ios/ is older and must not be treated as contrary new evidence; the native owner
may update its owned inventory to these source facts, retaining pending gates.

## Functional fail-closed boundary in this release

OffscreenSurface::configureSharedGraphicsContext rejects OpenGL and Unsupported
on iOS without mutating the chosen software backend. Software returns false on
Qt5, because this repository's paint-device path only exists for Qt6. On non-iOS,
valid OpenGL and Qt6 Software retain their existing behavior. Legacy direct
SharedObject::setSharedContext/setRenderTarget entrypoints terminate with closed
OVT_IOS_QML_GL_*_UNSUPPORTED markers on iOS, before invoking a GL API or changing
the process-global producer property. No fallback is silently selected.

Two focused tests compile and execute the ORIGINAL selection body in all four
Qt5/Qt6 and iOS/non-iOS combinations (Qt objects only are test substitutes), and
check direct-entry guard ordering. Full Qt/CMake/link evidence remains pending.

## Unsupported or unverified behavior

Qt's software adaptation does not render ShaderEffect or particle effects:
https://doc.qt.io/qt-6/qtquick-visualcanvas-adaptations-software.html
The current source does not supply a native-RHI replacement. Required surfaces
using those effects need explicit replacements or an exposed unsupported state;
an empty/transparent result is not success. This release does not claim that the
entire retained QML import closure has been inventoried for these components.

Native WebView embedding/offscreen composition, navigation/auth policy and
JITless script corpus remain distinct active Shared/native implementation work.
The old QtWebView component is NOT newly certified safe or renderer-compatible.
Diagnostic image patterns, flips and CPU-image counters are not real-scene
correctness, black-frame measurements or physical present receipts. No SH008
measurement may be derived from requested FPS, an upload marker or this inventory.

Consumer: iOS may import this exact Shared delta into its existing Qt6 stack.
Phone/Pico have no migration requirement and must not copy iOS rendering code
over their platform implementation. All original dependency/device gates remain.

## Local integration: diagnostic image export retirement

The screen and world-QML upload paths no longer save raw QML images into the
application Documents directory. Frame/sequence/source selectors are diagnostic
inputs, not authorization to retain account or private-world pixels. Their
`captureSaved` observation remains false and `capturePath` empty. Original
texture conversion, upload and display code is preserved; no existing image or
evidence file is deleted by this source change.

`test_diagnostic_image_exports.py` compiles each original export branch against
real Qt QImage/PNG I/O and a scratch-only Documents path boundary. All capture
selectors are enabled. Current branches create no file and preserve source image
pixels; the previous branches create an export and fail the same assertions.
The two branches are explicit extracted source regions, not a full renderer or
native screenshot acceptance test. The retained producer-boundary test checks
selection and both image consumers. This does not establish full privacy of
other diagnostic/export sinks, full QML effects support or real presentation.
