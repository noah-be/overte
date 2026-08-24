//
//  ApplicationOverlay.cpp
//  interface/src/ui/overlays
//
//  Created by Benjamin Arnold on 5/27/14.
//  Copyright 2014 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "ApplicationOverlay.h"

#include <algorithm>
#include <cmath>

#include <glm/gtc/type_ptr.hpp>

#include <avatar/AvatarManager.h>
#include <GLMHelpers.h>
#include <GLMHelpers.h>
#include <OffscreenUi.h>
#include <CursorManager.h>
#include <PathUtils.h>
#include <PerfStat.h>

#include "AudioClient.h"
#include "audio/AudioScope.h"
#include "Application.h"

#include "Util.h"
#include "ui/Stats.h"
#include "ui/AvatarInputs.h"
#include "OffscreenUi.h"
#include "InterfaceLogging.h"
#include <QQmlContext>

#if defined(Q_OS_IOS)
#include <QtCore/QDir>
#include <QtCore/QStandardPaths>
#include <QtGui/QColor>
#include <QtGui/QImage>
#include <QtGui/QScreen>
#include <shared/IOSRuntimeLogging.h>
#include <ui/TabletScriptingInterface.h>
#include <VirtualPadManager.h>
#endif

#if defined(ANDROID_APP_PHONE_INTERFACE)
#include <android/log.h>
#include <sys/system_properties.h>
#endif

const vec4 CONNECTION_STATUS_BORDER_COLOR{ 1.0f, 0.0f, 0.0f, 0.8f };
static const float ORTHO_NEAR_CLIP = -1000.0f;
static const float ORTHO_FAR_CLIP = 1000.0f;

#if defined(ANDROID_APP_PHONE_INTERFACE)
static bool isPhoneOverlayDepthEnabled();
static bool isPhoneOverlayCacheEnabled();
static float getPhoneOverlayScale();
#endif

ApplicationOverlay::ApplicationOverlay()
{
    auto geometryCache = DependencyManager::get<GeometryCache>();
    _domainStatusBorder = geometryCache->allocateID();
    _magnifierBorder = geometryCache->allocateID();
    _qmlGeometryId = geometryCache->allocateID();
#if defined(Q_OS_IOS)
    _iosVirtualPadBaseGeometryId = geometryCache->allocateID();
    _iosVirtualPadStickGeometryId = geometryCache->allocateID();
    _iosVirtualPadJumpGeometryId = geometryCache->allocateID();
    _iosVirtualPadHandshakeGeometryId = geometryCache->allocateID();
#endif
}

ApplicationOverlay::~ApplicationOverlay() {
    auto geometryCache = DependencyManager::get<GeometryCache>();
    if (geometryCache) {
        geometryCache->releaseID(_domainStatusBorder);
        geometryCache->releaseID(_magnifierBorder);
        geometryCache->releaseID(_qmlGeometryId);
#if defined(Q_OS_IOS)
        geometryCache->releaseID(_iosVirtualPadBaseGeometryId);
        geometryCache->releaseID(_iosVirtualPadStickGeometryId);
        geometryCache->releaseID(_iosVirtualPadJumpGeometryId);
        geometryCache->releaseID(_iosVirtualPadHandshakeGeometryId);
#endif
    }
}

// Renders the overlays either to a texture or to the screen
void ApplicationOverlay::renderOverlay(RenderArgs* renderArgs) {
    PROFILE_RANGE(render, __FUNCTION__);
#if defined(ANDROID_APP_PHONE_INTERFACE)
    const auto previousFramebuffer = _overlayFramebuffer;
    const auto previousFramebufferSize = previousFramebuffer ? previousFramebuffer->getSize() : glm::uvec2 {};
#endif
    buildFramebufferObject();
    
    if (!_overlayFramebuffer) {
        return; // we can't do anything without our frame buffer.
    }

#if defined(ANDROID_APP_PHONE_INTERFACE)
    const bool framebufferChanged = !previousFramebuffer || previousFramebuffer != _overlayFramebuffer ||
        previousFramebufferSize != _overlayFramebuffer->getSize();
#if !defined(DISABLE_QML)
    const bool newQmlTexture = updatePhoneQmlTexture();
#else
    const bool newQmlTexture = false;
#endif
    const bool cacheEnabled = isPhoneOverlayCacheEnabled();
    // Phone 2D overlays currently derive from QmlOverlay, whose render() is empty;
    // their pixels arrive in the QML texture above. If a future phone overlay draws
    // directly into this batch, it must invalidate this cache before cache-by-default
    // can be considered safe.
    const bool reuseComposite = cacheEnabled && _phoneOverlayCompositeValid &&
        !framebufferChanged && !newQmlTexture;
    ++_phoneOverlayCacheSamples;
    _phoneOverlayCacheHits += reuseComposite ? 1 : 0;
    _phoneOverlayCacheMisses += reuseComposite ? 0 : 1;
    _phoneOverlayCacheNewTextures += newQmlTexture ? 1 : 0;
    _phoneOverlayCacheResizes += framebufferChanged ? 1 : 0;
    if ((_phoneOverlayCacheSamples % 300) == 0) {
        __android_log_print(ANDROID_LOG_INFO, "OvertePhoneGraphics",
            "overlay_cache_enabled=%d overlay_cache_samples=%u overlay_cache_hits=%u "
            "overlay_cache_misses=%u overlay_cache_new_textures=%u overlay_cache_resizes=%u",
            cacheEnabled ? 1 : 0, _phoneOverlayCacheSamples, _phoneOverlayCacheHits,
            _phoneOverlayCacheMisses, _phoneOverlayCacheNewTextures, _phoneOverlayCacheResizes);
    }
    if (reuseComposite) {
        renderArgs->_batch = nullptr;
        return;
    }
#endif

    // Execute the batch into our framebuffer
    doInBatch("ApplicationOverlay::render", renderArgs->_context, [&](gpu::Batch& batch) {
        PROFILE_RANGE_BATCH(batch, "ApplicationOverlayRender");
        renderArgs->_batch = &batch;
        batch.enableStereo(false);

        int width = _overlayFramebuffer->getWidth();
        int height = _overlayFramebuffer->getHeight();

        batch.setViewportTransform(glm::ivec4(0, 0, width, height));
        batch.setFramebuffer(_overlayFramebuffer);

        glm::vec4 color { 0.0f, 0.0f, 0.0f, 0.0f };
        float depth = 1.0f;
        int stencil = 0;
#if defined(ANDROID_APP_PHONE_INTERFACE)
        const auto clearMask = gpu::Framebuffer::BUFFER_COLOR0 |
            (isPhoneOverlayDepthEnabled() ? gpu::Framebuffer::BUFFER_DEPTH : 0);
        batch.clearFramebuffer(clearMask, color, depth, stencil);
#else
        batch.clearFramebuffer(gpu::Framebuffer::BUFFER_COLOR0 | gpu::Framebuffer::BUFFER_DEPTH, color, depth, stencil);
#endif

        // Now render the overlay components together into a single texture
#if !defined(ANDROID_APP_PHONE_INTERFACE) && !defined(Q_OS_IOS)
        renderDomainConnectionStatusBorder(renderArgs); // renders the connected domain line
#endif
        renderOverlays(renderArgs); // renders Scripts Overlay and AudioScope
#if !defined(DISABLE_QML)
        renderQmlUi(renderArgs); // renders a unit quad with the QML UI texture, and the text overlays from scripts
#endif
#if defined(Q_OS_IOS)
        // The legacy OpenGL display plugin draws this after composition on
        // Android. iOS uses Vulkan, so put the same controls into the ordinary
        // HUD framebuffer where VulkanDisplayPlugin can composite them.
        renderIOSVirtualPad(renderArgs);
#endif
    });

    renderArgs->_batch = nullptr; // so future users of renderArgs don't try to use our batch
#if defined(ANDROID_APP_PHONE_INTERFACE)
    _phoneOverlayCompositeValid = true;
#endif
}

void ApplicationOverlay::renderQmlUi(RenderArgs* renderArgs) {
    PROFILE_RANGE(render, __FUNCTION__);

#if defined(Q_OS_IOS)
    updateIOSQmlTexture();
    if (!_uiTexture) {
        return;
    }
#elif defined(ANDROID_APP_PHONE_INTERFACE)
    // The phone path fetched and published any new texture before deciding
    // whether this composite batch can be skipped.
#else
    if (!_uiTexture) {
        _uiTexture = gpu::Texture::createExternal(OffscreenQmlSurface::getDiscardLambda());
        _uiTexture->setSource(__FUNCTION__);
    }
    // Once we move UI rendering and screen rendering to different
    // threads, we need to use a sync object to deteremine when
    // the current UI texture is no longer being read from, and only
    // then release it back to the UI for re-use
    auto offscreenUI = DependencyManager::get<OffscreenUi>();

    OffscreenQmlSurface::TextureAndFence newTextureAndFence;
    bool newTextureAvailable = offscreenUI ? offscreenUI->fetchTexture(newTextureAndFence) : false;
    if (newTextureAvailable) {
        _uiTexture->setExternalTexture(newTextureAndFence.first, newTextureAndFence.second);
        _uiTexture->setSize(offscreenUI->size().width(), offscreenUI->size().height());
    }
#endif
    auto geometryCache = DependencyManager::get<GeometryCache>();
    gpu::Batch& batch = *renderArgs->_batch;
    geometryCache->useSimpleDrawPipeline(batch);
    batch.setProjectionTransform(mat4());
    batch.setModelTransform(Transform());
    batch.resetViewTransform();
    batch.setResourceTexture(0, _uiTexture);
    geometryCache->renderUnitQuad(batch, glm::vec4(1), _qmlGeometryId);
    batch.setResourceTexture(0, nullptr);
}

#if defined(Q_OS_IOS)
bool ApplicationOverlay::updateIOSQmlTexture() {
    auto offscreenUI = DependencyManager::get<OffscreenUi>();
    QImage sourceImage;
    if (!offscreenUI || !offscreenUI->fetchImage(sourceImage)) {
        return false;
    }

    QImage uploadImage = sourceImage.convertToFormat(QImage::Format_RGBA8888);
    if (uploadImage.isNull() || uploadImage.width() <= 0 || uploadImage.height() <= 0) {
        logIOSRuntimeMarker(
            "OVERTE_IOS_SCREEN_QML_FRAME_GATE stage=invalid-cpu-frame",
            "source_size=", sourceImage.size());
        return false;
    }

    // Qt Quick software frames use a top-left origin while the ordinary GPU
    // texture sampled by ApplicationOverlay uses the opposite vertical axis.
    // Keep an AFC-editable escape hatch so a physical-device run can test the
    // alternate orientation without another build.
    if (iosRuntimeDiagnosticBool("screenQmlFlipVertical", true)) {
        uploadImage = uploadImage.mirrored(false, true);
    }

    // The display backend retires the previous frame before starting the next
    // one.  Keep a small ring anyway so the UI producer never mutates the CPU
    // storage still retained by a queued frame.  Reusing these Texture objects
    // also lets the iOS Vulkan backend update four fixed VkImages instead of
    // creating and destroying a 5+ MiB image for every software-QML frame.
    auto& texture = _iosQmlTextureRing[_iosQmlTextureRingIndex];
    const bool textureMatches = texture &&
        texture->getWidth() == static_cast<uint16_t>(uploadImage.width()) &&
        texture->getHeight() == static_cast<uint16_t>(uploadImage.height());
    if (!textureMatches) {
        texture = gpu::Texture::createStrict(
            gpu::Element::COLOR_RGBA_32,
            static_cast<uint16_t>(uploadImage.width()),
            static_cast<uint16_t>(uploadImage.height()),
            1,
            Sampler(Sampler::FILTER_MIN_MAG_LINEAR, Sampler::WRAP_CLAMP));
        texture->setStoredMipFormat(gpu::Element::COLOR_RGBA_32);
        texture->setUsage(gpu::Texture::Usage::Builder().withColor().withAlpha().build());
        texture->setSource("ApplicationOverlayIOSSoftware");
    }
    texture->assignStoredMip(
        0,
        static_cast<gpu::Size>(uploadImage.sizeInBytes()),
        reinterpret_cast<const gpu::Byte*>(uploadImage.constBits()));
    _uiTexture = texture;
    _iosQmlTextureRingIndex =
        (_iosQmlTextureRingIndex + 1) % IOS_QML_TEXTURE_RING_SIZE;

    ++_iosQmlFrameOrdinal;
    const auto diagnosticFrames = iosRuntimeDiagnosticIntSet(
        "screenQmlCaptureFrameOrdinals", 1, 1000000);
    const int captureSequence = iosRuntimeDiagnosticInt(
        "screenQmlCaptureLatestFrameSequence", -1, -1, 1000000);
    const bool firstFrame = _iosQmlFrameOrdinal == 1;
    const bool selectedFrame = diagnosticFrames.contains(static_cast<int>(_iosQmlFrameOrdinal));
    const bool selectedSequence = captureSequence >= 0 &&
        captureSequence != _lastIOSQmlCaptureSequence;
    if (firstFrame || selectedFrame || selectedSequence) {
        quint64 sampledPixels { 0 };
        quint64 alphaNonzeroPixels { 0 };
        quint64 nonBlackPixels { 0 };
        const quint64 totalPixels = static_cast<quint64>(uploadImage.width()) * uploadImage.height();
        constexpr quint64 MAX_DIAGNOSTIC_SAMPLES { 65536 };
        const quint64 sampleStride = std::max<quint64>(1, totalPixels / MAX_DIAGNOSTIC_SAMPLES);
        for (quint64 offset = 0; offset < totalPixels; offset += sampleStride) {
            const int y = static_cast<int>(offset / uploadImage.width());
            const int x = static_cast<int>(offset % uploadImage.width());
            const QColor pixel = uploadImage.pixelColor(x, y);
            ++sampledPixels;
            alphaNonzeroPixels += pixel.alpha() != 0;
            nonBlackPixels += pixel.alpha() != 0 &&
                (pixel.red() != 0 || pixel.green() != 0 || pixel.blue() != 0);
        }

        QString capturePath;
        bool captureSaved { false };
        if (selectedFrame || selectedSequence ||
                iosRuntimeDiagnosticBool("captureFirstScreenQmlFrame", false)) {
            capturePath = QDir(QStandardPaths::writableLocation(QStandardPaths::DocumentsLocation))
                .filePath(QStringLiteral("Overte-iOS-Screen-QML-%1.png").arg(_iosQmlFrameOrdinal));
            captureSaved = uploadImage.save(capturePath, "PNG");
        }
        if (captureSequence >= 0) {
            _lastIOSQmlCaptureSequence = captureSequence;
        }
        const auto corner = uploadImage.pixelColor(0, 0);
        const auto center = uploadImage.pixelColor(uploadImage.width() / 2, uploadImage.height() / 2);
        logIOSRuntimeMarker(
            "OVERTE_IOS_SCREEN_QML_FRAME_GATE stage=cpu-frame-uploaded",
            "ordinal=", _iosQmlFrameOrdinal,
            "size=", uploadImage.size(),
            "sampled_pixels=", sampledPixels,
            "alpha_nonzero_pixels=", alphaNonzeroPixels,
            "non_black_pixels=", nonBlackPixels,
            "corner_rgba=", QStringLiteral("%1,%2,%3,%4")
                .arg(corner.red()).arg(corner.green()).arg(corner.blue()).arg(corner.alpha()),
            "center_rgba=", QStringLiteral("%1,%2,%3,%4")
                .arg(center.red()).arg(center.green()).arg(center.blue()).arg(center.alpha()),
            "capture_saved=", captureSaved,
            "capture_sequence=", captureSequence,
            "capture_path=", capturePath);
    }
    return true;
}

namespace {
gpu::TexturePointer makeIOSVirtualPadTexture(const QString& path, int pixelSize, const char* source) {
    QImage image(path);
    if (image.isNull() || pixelSize <= 0) {
        return {};
    }
    image = image.convertToFormat(QImage::Format_RGBA8888)
        .scaled(pixelSize, pixelSize, Qt::KeepAspectRatio, Qt::SmoothTransformation)
        .mirrored(false, true);
    if (image.isNull()) {
        return {};
    }
    auto texture = gpu::Texture::createStrict(
        gpu::Element::COLOR_RGBA_32,
        static_cast<uint16_t>(image.width()),
        static_cast<uint16_t>(image.height()),
        1,
        Sampler(Sampler::FILTER_MIN_MAG_LINEAR, Sampler::WRAP_CLAMP));
    texture->setStoredMipFormat(gpu::Element::COLOR_RGBA_32);
    texture->assignStoredMip(
        0,
        static_cast<gpu::Size>(image.sizeInBytes()),
        reinterpret_cast<const gpu::Byte*>(image.constBits()));
    texture->setUsage(gpu::Texture::Usage::Builder().withColor().withAlpha().build());
    texture->setSource(source);
    return texture;
}
}

void ApplicationOverlay::initializeIOSVirtualPadTextures() {
    if (_iosVirtualPadBaseTexture && _iosVirtualPadStickTexture &&
            _iosVirtualPadJumpTexture && _iosVirtualPadHandshakeTexture) {
        return;
    }

    const auto screen = qApp->primaryScreen();
    const qreal reportedDpi = screen ? screen->physicalDotsPerInch() : 0.0;
    const qreal dpi = std::isfinite(reportedDpi) && reportedDpi > 0.0 ? reportedDpi : 264.0;
    const int configuredScalePercent = iosRuntimeDiagnosticInt(
        "virtualPadScalePercent", 100, 50, 200);
    const float scale = static_cast<float>(configuredScalePercent) / 100.0f;
    _iosVirtualPadPixelSize = static_cast<float>(
        dpi * VirtualPad::Manager::BASE_DIAMETER_PIXELS / VirtualPad::Manager::DPI) * scale;
    _iosVirtualPadButtonPixelSize = static_cast<float>(
        dpi * VirtualPad::Manager::BTN_FULL_PIXELS / VirtualPad::Manager::DPI) * scale;

    _iosVirtualPadBaseTexture = makeIOSVirtualPadTexture(
        PathUtils::resourcesPath() + "images/analog_stick_base.png",
        std::lround(_iosVirtualPadPixelSize),
        "iOS virtual pad base");
    _iosVirtualPadStickTexture = makeIOSVirtualPadTexture(
        PathUtils::resourcesPath() + "images/analog_stick.png",
        std::lround(_iosVirtualPadPixelSize),
        "iOS virtual pad stick");
    _iosVirtualPadJumpTexture = makeIOSVirtualPadTexture(
        PathUtils::resourcesPath() + "images/fly.png",
        std::lround(_iosVirtualPadButtonPixelSize),
        "iOS virtual pad jump");
    _iosVirtualPadHandshakeTexture = makeIOSVirtualPadTexture(
        PathUtils::resourcesPath() + "images/handshake.png",
        std::lround(_iosVirtualPadButtonPixelSize),
        "iOS virtual pad handshake");

    logIOSRuntimeMarker(
        "OVERTE_IOS_TOUCH_UI_GATE stage=virtual-pad-textures",
        "ready=", static_cast<bool>(_iosVirtualPadBaseTexture && _iosVirtualPadStickTexture &&
            _iosVirtualPadJumpTexture && _iosVirtualPadHandshakeTexture),
        "dpi=", dpi,
        "base_pixels=", _iosVirtualPadPixelSize,
        "button_pixels=", _iosVirtualPadButtonPixelSize);
}

void ApplicationOverlay::renderIOSVirtualPad(RenderArgs* renderArgs) {
    auto& manager = VirtualPad::Manager::instance();
    const bool forceVisible = iosRuntimeDiagnosticBool("virtualPadForceVisible", false);
    if ((!manager.isEnabled() || manager.isHidden() || !manager.getLeftVirtualPad()->isShown()) && !forceVisible) {
        return;
    }
    initializeIOSVirtualPadTextures();
    if (!_iosVirtualPadBaseTexture || !_iosVirtualPadStickTexture ||
            !_iosVirtualPadJumpTexture || !_iosVirtualPadHandshakeTexture) {
        return;
    }

    const glm::vec2 targetSize(
        static_cast<float>(_overlayFramebuffer->getWidth()),
        static_cast<float>(_overlayFramebuffer->getHeight()));
    const auto tablet = DependencyManager::get<TabletScriptingInterface>();
    const QVariantMap metrics = tablet ? tablet->getTouchUiRuntimeMetrics() : QVariantMap();
    const bool metricsValid = metrics.value("valid").toBool();
    const QSize logicalScreenSize = metricsValid
        ? QSize(
            std::max(1, metrics.value("surfaceWidth").toInt() -
                metrics.value("safeInsetLeft").toInt() -
                metrics.value("safeInsetRight").toInt()),
            std::max(1, metrics.value("surfaceHeight").toInt() -
                metrics.value("safeInsetTop").toInt() -
                metrics.value("safeInsetBottom").toInt()))
        : QSize(static_cast<int>(targetSize.x), static_cast<int>(targetSize.y));
    const glm::vec2 logicalSize(
        std::max(1, logicalScreenSize.width()),
        std::max(1, logicalScreenSize.height()));
    const glm::vec2 coordinateScale = targetSize / logicalSize;

    auto mapPoint = [&](glm::vec2 point) {
        // Touch input and control layout are already expressed relative to
        // the safe-content origin, exactly like this Vulkan HUD target.
        point *= coordinateScale;
        return glm::vec2(
            2.0f * point.x / targetSize.x - 1.0f,
            1.0f - 2.0f * point.y / targetSize.y);
    };
    auto draw = [&](const gpu::TexturePointer& texture, const glm::vec2& logicalPoint,
                    float logicalPixelSize, int geometryId) {
        const glm::vec2 center = mapPoint(logicalPoint);
        const glm::vec2 pixelScale = coordinateScale * logicalPixelSize;
        const glm::mat4 transform = glm::scale(
            glm::translate(glm::mat4(), glm::vec3(center, 0.0f)),
            glm::vec3(pixelScale.x / targetSize.x, pixelScale.y / targetSize.y, 1.0f));
        auto geometryCache = DependencyManager::get<GeometryCache>();
        gpu::Batch& batch = *renderArgs->_batch;
        batch.setResourceTexture(0, texture);
        batch.setModelTransform(transform);
        geometryCache->renderUnitQuad(batch, glm::vec4(1.0f), geometryId);
    };

    auto basePoint = manager.getLeftVirtualPad()->getFirstTouch();
    auto stickPoint = manager.getLeftVirtualPad()->getCurrentTouch();
    auto jumpPoint = manager.getButtonPosition(VirtualPad::Manager::Button::JUMP);
    auto handshakePoint = manager.getButtonPosition(VirtualPad::Manager::Button::HANDSHAKE);
    if (forceVisible && (basePoint.x <= 0.0f || basePoint.y <= 0.0f)) {
        basePoint = glm::vec2(logicalSize.x * 0.13f, logicalSize.y * 0.78f);
        stickPoint = basePoint;
    }
    if (forceVisible && (jumpPoint.x <= 0.0f || jumpPoint.y <= 0.0f)) {
        jumpPoint = glm::vec2(logicalSize.x * 0.90f, logicalSize.y * 0.80f);
        handshakePoint = glm::vec2(logicalSize.x * 0.90f, logicalSize.y * 0.60f);
    }

    auto geometryCache = DependencyManager::get<GeometryCache>();
    gpu::Batch& batch = *renderArgs->_batch;
    geometryCache->useSimpleDrawPipeline(batch);
    batch.setProjectionTransform(glm::mat4());
    batch.resetViewTransform();
    draw(_iosVirtualPadBaseTexture, basePoint, _iosVirtualPadPixelSize, _iosVirtualPadBaseGeometryId);
    draw(_iosVirtualPadStickTexture, stickPoint, _iosVirtualPadPixelSize, _iosVirtualPadStickGeometryId);
    draw(_iosVirtualPadJumpTexture, jumpPoint, _iosVirtualPadButtonPixelSize, _iosVirtualPadJumpGeometryId);
    draw(_iosVirtualPadHandshakeTexture, handshakePoint, _iosVirtualPadButtonPixelSize, _iosVirtualPadHandshakeGeometryId);
    batch.setResourceTexture(0, nullptr);

    static std::once_flag marker;
    std::call_once(marker, [&] {
        logIOSRuntimeMarker(
            "OVERTE_IOS_TOUCH_UI_GATE stage=virtual-pad-composited",
            "target_size=", QSize(static_cast<int>(targetSize.x), static_cast<int>(targetSize.y)),
            "logical_size=", logicalScreenSize,
            "coordinate_space=safe-content",
            "base=", QStringLiteral("%1,%2").arg(basePoint.x).arg(basePoint.y),
            "jump=", QStringLiteral("%1,%2").arg(jumpPoint.x).arg(jumpPoint.y),
            "forced=", forceVisible);
    });
}
#endif

#if defined(ANDROID_APP_PHONE_INTERFACE)
bool ApplicationOverlay::updatePhoneQmlTexture() {
    if (!_uiTexture) {
        _uiTexture = gpu::Texture::createExternal(
            OffscreenQmlSurface::getDiscardLambda(),
            Sampler(Sampler::FILTER_MIN_MAG_LINEAR, Sampler::WRAP_CLAMP));
        _uiTexture->setSource(__FUNCTION__);
    }

    auto offscreenUI = DependencyManager::get<OffscreenUi>();
    OffscreenQmlSurface::TextureAndFence newTextureAndFence;
    const bool newTextureAvailable = offscreenUI ? offscreenUI->fetchTexture(newTextureAndFence) : false;
    if (newTextureAvailable) {
        _uiTexture->setExternalTexture(newTextureAndFence.first, newTextureAndFence.second);
        _uiTexture->setSize(offscreenUI->size().width(), offscreenUI->size().height());
    }
    return newTextureAvailable;
}
#endif

void ApplicationOverlay::renderOverlays(RenderArgs* renderArgs) {
    PROFILE_RANGE(render, __FUNCTION__);

    gpu::Batch& batch = *renderArgs->_batch;
    auto geometryCache = DependencyManager::get<GeometryCache>();
    geometryCache->useSimpleDrawPipeline(batch);
    auto textureCache = DependencyManager::get<TextureCache>();
    batch.setResourceTexture(0, textureCache->getWhiteTexture());
    int width = renderArgs->_viewport.z;
    int height = renderArgs->_viewport.w;
    mat4 legacyProjection = glm::ortho<float>(0, width, height, 0, ORTHO_NEAR_CLIP, ORTHO_FAR_CLIP);
    batch.setProjectionTransform(legacyProjection);
    batch.setModelTransform(Transform());
    batch.resetViewTransform();

    // Render all of the Script based "HUD" aka 2D overlays.
    qApp->getOverlays().render(renderArgs);
}

void ApplicationOverlay::renderDomainConnectionStatusBorder(RenderArgs* renderArgs) {
    auto geometryCache = DependencyManager::get<GeometryCache>();
    static std::once_flag once;
    std::call_once(once, [&] {
        QVector<vec2> points;
        static const float B = 0.99f;
        points.push_back(vec2(-B));
        points.push_back(vec2(B, -B));
        points.push_back(vec2(B));
        points.push_back(vec2(-B, B));
        points.push_back(vec2(-B));
        geometryCache->updateVertices(_domainStatusBorder, points, CONNECTION_STATUS_BORDER_COLOR);
    });
    auto nodeList = DependencyManager::get<NodeList>();
    // A serverless scene intentionally has no domain connection. Treat it as a
    // valid world instead of covering its HUD with the disconnected red frame.
    if (nodeList &&
            !qApp->isServerlessMode() &&
            !nodeList->getDomainHandler().isServerless() &&
            !nodeList->getDomainHandler().isConnected()) {
        gpu::Batch& batch = *renderArgs->_batch;
        auto geometryCache = DependencyManager::get<GeometryCache>();
        geometryCache->useSimpleDrawPipeline(batch);
        batch.setProjectionTransform(mat4());
        batch.setModelTransform(Transform());
        batch.resetViewTransform();
        batch.setResourceTexture(0, DependencyManager::get<TextureCache>()->getWhiteTexture());
        // FIXME: THe line width of CONNECTION_STATUS_BORDER_LINE_WIDTH is not supported anymore, we ll need a workaround

        // TODO animate the disconnect border for some excitement while not connected?
        //double usecs = usecTimestampNow();
        //double secs = usecs / 1000000.0;
        //float scaleAmount = 1.0f + (0.01f * sin(secs * 5.0f));
        //batch.setModelTransform(glm::scale(mat4(), vec3(scaleAmount)));

        geometryCache->renderVertices(batch, gpu::LINE_STRIP, _domainStatusBorder);
    }
}

static const auto COLOR_FORMAT = gpu::Element(gpu::VEC4, gpu::NUINT8, gpu::RGBA);
static const auto DEFAULT_SAMPLER = Sampler(Sampler::FILTER_MIN_MAG_LINEAR);
static const auto DEPTH_FORMAT = gpu::Element(gpu::SCALAR, gpu::FLOAT, gpu::DEPTH);

#if defined(ANDROID_APP_PHONE_INTERFACE)
static bool isPhoneOverlayDepthEnabled() {
    static const bool enabled = [] {
        char propertyValue[PROP_VALUE_MAX] {};
        if (__system_property_get("debug.overte.phone_overlay_depth", propertyValue) <= 0) {
            return false;
        }

        const auto requested = QByteArray(propertyValue).trimmed().toLower();
        if (requested == "1" || requested == "on" || requested == "true" || requested == "enabled") {
            return true;
        }
        if (requested == "0" || requested == "off" || requested == "false" || requested == "disabled") {
            return false;
        }
        return false;
    }();
    return enabled;
}

static bool isPhoneOverlayCacheEnabled() {
    static const bool enabled = [] {
        char propertyValue[PROP_VALUE_MAX] {};
        if (__system_property_get("debug.overte.phone_overlay_cache", propertyValue) <= 0) {
            return true;
        }

        const auto requested = QByteArray(propertyValue).trimmed().toLower();
        if (requested == "1" || requested == "on" || requested == "true" || requested == "enabled") {
            return true;
        }
        if (requested == "0" || requested == "off" || requested == "false" || requested == "disabled") {
            return false;
        }
        return false;
    }();
    return enabled;
}

static float getPhoneOverlayScale() {
    static const float scale = [] {
        char propertyValue[PROP_VALUE_MAX] {};
        if (__system_property_get("debug.overte.phone_overlay_scale", propertyValue) <= 0) {
            return 1.0f;
        }

        bool parsed { false };
        const double requested = QByteArray(propertyValue).trimmed().toDouble(&parsed);
        if (!parsed || !std::isfinite(requested)) {
            return 1.0f;
        }
        return static_cast<float>(std::max(0.5, std::min(1.0, requested)));
    }();
    return scale;
}
#endif

void ApplicationOverlay::buildFramebufferObject() {
    PROFILE_RANGE(render, __FUNCTION__);

    const auto logicalSize = glm::uvec2(qApp->getUiSize());
#if defined(ANDROID_APP_PHONE_INTERFACE)
    const float overlayScale = getPhoneOverlayScale();
    const auto targetSize = glm::uvec2(
        std::max(1L, std::lround(static_cast<double>(logicalSize.x) * overlayScale)),
        std::max(1L, std::lround(static_cast<double>(logicalSize.y) * overlayScale)));
#else
    const auto targetSize = logicalSize;
#endif
    if (!_overlayFramebuffer || targetSize != _overlayFramebuffer->getSize()) {
        _overlayFramebuffer = gpu::FramebufferPointer(gpu::Framebuffer::create("ApplicationOverlay"));
    }

    const auto width = targetSize.x;
    const auto height = targetSize.y;
#if defined(ANDROID_APP_PHONE_INTERFACE)
    const bool overlayDepthEnabled = isPhoneOverlayDepthEnabled();
    static std::once_flag phoneOverlayDepthMarker;
    std::call_once(phoneOverlayDepthMarker, [overlayDepthEnabled, overlayScale, logicalSize, width, height] {
        constexpr double BYTES_PER_MIB { 1024.0 * 1024.0 };
        const double estimatedColorMiB =
            static_cast<double>(width) * static_cast<double>(height) * 4.0 / BYTES_PER_MIB;
        const double estimatedDepthMiB = overlayDepthEnabled
            ? static_cast<double>(width) * static_cast<double>(height) * sizeof(float) / BYTES_PER_MIB
            : 0.0;
        __android_log_print(ANDROID_LOG_INFO, "OvertePhoneGraphics",
            "overlay_depth_enabled=%d overlay_logical_width=%u overlay_logical_height=%u "
            "overlay_target_width=%u overlay_target_height=%u overlay_scale=%.3f "
            "overlay_color_estimated_mib=%.2f overlay_depth_estimated_mib=%.2f",
            overlayDepthEnabled ? 1 : 0, logicalSize.x, logicalSize.y, width, height, overlayScale,
            estimatedColorMiB, estimatedDepthMiB);
    });
    if (overlayDepthEnabled && !_overlayFramebuffer->getDepthStencilBuffer()) {
#else
    if (!_overlayFramebuffer->getDepthStencilBuffer()) {
#endif
        auto overlayDepthTexture = gpu::Texture::createRenderBuffer(DEPTH_FORMAT, width, height, gpu::Texture::SINGLE_MIP, DEFAULT_SAMPLER);
        _overlayFramebuffer->setDepthStencilBuffer(overlayDepthTexture, DEPTH_FORMAT);
    }

    if (!_overlayFramebuffer->getRenderBuffer(0)) {
        const Sampler OVERLAY_SAMPLER(Sampler::FILTER_MIN_MAG_LINEAR, Sampler::WRAP_CLAMP);
        auto colorBuffer = gpu::Texture::createRenderBuffer(COLOR_FORMAT, width, height, gpu::Texture::SINGLE_MIP, OVERLAY_SAMPLER);
        _overlayFramebuffer->setRenderBuffer(0, colorBuffer);
    }
}

gpu::TexturePointer ApplicationOverlay::getOverlayTexture() {
    if (!_overlayFramebuffer) {
        return gpu::TexturePointer();
    }
    return _overlayFramebuffer->getRenderBuffer(0);
}
