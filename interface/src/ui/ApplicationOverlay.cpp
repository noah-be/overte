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
}

ApplicationOverlay::~ApplicationOverlay() {
    auto geometryCache = DependencyManager::get<GeometryCache>();
    if (geometryCache) {
        geometryCache->releaseID(_domainStatusBorder);
        geometryCache->releaseID(_magnifierBorder);
        geometryCache->releaseID(_qmlGeometryId);
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
#if !defined(ANDROID_APP_PHONE_INTERFACE)
        renderDomainConnectionStatusBorder(renderArgs); // renders the connected domain line
#endif
        renderOverlays(renderArgs); // renders Scripts Overlay and AudioScope
#if !defined(DISABLE_QML)
#if defined(OVERTE_IOS_VULKAN_DISABLE_EXTERNAL_GL_INTEROP)
        // The desktop QML texture is an external GL texture. MoltenVK cannot
        // import it on iOS, so drawing its fail-closed fallback would cover
        // the completed scene with opaque black. Keep the transparent overlay
        // target until a native IOSurface/Metal import path is available.
#else
        renderQmlUi(renderArgs); // renders a unit quad with the QML UI texture, and the text overlays from scripts
#endif
#endif
    });

    renderArgs->_batch = nullptr; // so future users of renderArgs don't try to use our batch
#if defined(ANDROID_APP_PHONE_INTERFACE)
    _phoneOverlayCompositeValid = true;
#endif
}

void ApplicationOverlay::renderQmlUi(RenderArgs* renderArgs) {
    PROFILE_RANGE(render, __FUNCTION__);

#if defined(ANDROID_APP_PHONE_INTERFACE)
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
