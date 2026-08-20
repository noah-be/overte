//
//  GraphicsEngine.cpp
//
//  Created by Sam Gateau on 29/6/2018.
//  Copyright 2018 High Fidelity, Inc.
//  Copyright 2023 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//  SPDX-License-Identifier: Apache-2.0
//
#include "GraphicsEngine.h"

#include <shared/GlobalAppProperties.h>

#include "WorldBox.h"
#include "LODManager.h"

#include <GeometryCache.h>
#include <TextureCache.h>
#include <FramebufferCache.h>
#include <UpdateSceneTask.h>
#include <RenderViewTask.h>
#include <SecondaryCamera.h>

#include "RenderEventHandler.h"

#include <gpu/Batch.h>
#include <gpu/Context.h>
#ifdef USE_GL
#include <gpu/gl/GLBackend.h>
#else
#include <gpu/vk/VKBackend.h>
#endif
#include <display-plugins/DisplayPlugin.h>

#include <display-plugins/CompositorHelper.h>
#include <QMetaObject>
#if defined(ANDROID_APP_PICO_INTERFACE)
#include <QCoreApplication>
#include <QFont>
#include <QImage>
#include <QPainter>
#include <cmath>
#endif
#include "ui/Stats.h"
#include "Application.h"

GraphicsEngine::GraphicsEngine() {
    const QString SPLASH_SKYBOX { "{\"ProceduralEntity\":{ \"version\":2, \"shaderUrl\":\"qrc:///shaders/splashSkybox.frag\" } }" };
    _splashScreen->parse(SPLASH_SKYBOX);
    const QUrl SPLASH_IMAGE { PathUtils::resourcesUrl("images/splashShaders.png") };
    _texture = DependencyManager::get<TextureCache>()->getTexture(SPLASH_IMAGE);

#if defined(ANDROID_APP_PICO_INTERFACE)
    _loadingLogo = DependencyManager::get<TextureCache>()->getTexture(
        PathUtils::resourcesUrl("images/brand-banner.svg"));
    _loadingStatusTextures[static_cast<size_t>(LoadingPhase::STARTING)] =
        makeLoadingStatusTexture(
            QCoreApplication::translate("PicoLoadingScreen", "Starting Overte"),
            QCoreApplication::translate("PicoLoadingScreen", "Initializing the renderer"));
    _loadingStatusTextures[static_cast<size_t>(LoadingPhase::CONNECTING)] =
        makeLoadingStatusTexture(
            QCoreApplication::translate("PicoLoadingScreen", "Connecting to world"),
            QCoreApplication::translate("PicoLoadingScreen", "Contacting the domain server"));
    _loadingStatusTextures[static_cast<size_t>(LoadingPhase::CONNECTED)] =
        makeLoadingStatusTexture(
            QCoreApplication::translate("PicoLoadingScreen", "Connected"),
            QCoreApplication::translate("PicoLoadingScreen", "Waiting for initial scene data"));
    _loadingStatusTextures[static_cast<size_t>(LoadingPhase::RECEIVING_WORLD)] =
        makeLoadingStatusTexture(
            QCoreApplication::translate("PicoLoadingScreen", "Receiving world data"),
            QCoreApplication::translate("PicoLoadingScreen", "Loading nearby entities"));
    _loadingStatusTextures[static_cast<size_t>(LoadingPhase::RECOVERING_WORLD)] =
        makeLoadingStatusTexture(
            QCoreApplication::translate("PicoLoadingScreen", "Receiving world data"),
            QCoreApplication::translate("PicoLoadingScreen", "Recovering missing entity packets"));
    _loadingStatusTextures[static_cast<size_t>(LoadingPhase::DOWNLOADING_RESOURCES)] =
        makeLoadingStatusTexture(
            QCoreApplication::translate("PicoLoadingScreen", "Downloading world resources"),
            QCoreApplication::translate("PicoLoadingScreen", "Models, textures, and collision data"));
    _loadingStatusTextures[static_cast<size_t>(LoadingPhase::PROCESSING_RESOURCES)] =
        makeLoadingStatusTexture(
            QCoreApplication::translate("PicoLoadingScreen", "Processing world resources"),
            QCoreApplication::translate("PicoLoadingScreen", "Preparing models and collision data"));
    _loadingStatusTextures[static_cast<size_t>(LoadingPhase::PREPARING_WORLD)] =
        makeLoadingStatusTexture(
            QCoreApplication::translate("PicoLoadingScreen", "Preparing nearby entities"),
            QCoreApplication::translate("PicoLoadingScreen", "Models, textures, and collision shapes"));
    _loadingStatusTextures[static_cast<size_t>(LoadingPhase::UPLOADING_RESOURCES)] =
        makeLoadingStatusTexture(
            QCoreApplication::translate("PicoLoadingScreen", "Uploading world resources"),
            QCoreApplication::translate("PicoLoadingScreen", "Transferring textures to the GPU"));
    _loadingStatusTextures[static_cast<size_t>(LoadingPhase::STARTING_PHYSICS)] =
        makeLoadingStatusTexture(
            QCoreApplication::translate("PicoLoadingScreen", "Starting physics"),
            QCoreApplication::translate("PicoLoadingScreen", "Enabling movement and simulation"));
    _loadingStatusTextures[static_cast<size_t>(LoadingPhase::FINALIZING_SCENE)] =
        makeLoadingStatusTexture(
            QCoreApplication::translate("PicoLoadingScreen", "Finalizing world"),
            QCoreApplication::translate("PicoLoadingScreen", "Preparing the first playable frame"));
    _loadingStatusTextures[static_cast<size_t>(LoadingPhase::READY)] =
        makeLoadingStatusTexture(
            QCoreApplication::translate("PicoLoadingScreen", "World ready"),
            QCoreApplication::translate("PicoLoadingScreen", "You can start exploring"));
    _loadingStatusTextures[static_cast<size_t>(LoadingPhase::WAITING_FOR_WORLD)] =
        makeLoadingStatusTexture(
            QCoreApplication::translate("PicoLoadingScreen", "Waiting for world data"),
            QCoreApplication::translate("PicoLoadingScreen", "No new scene data received yet"));
    _loadingStatusTextures[static_cast<size_t>(LoadingPhase::WORLD_SERVER_UNAVAILABLE)] =
        makeLoadingStatusTexture(
            QCoreApplication::translate("PicoLoadingScreen", "World server unavailable"),
            QCoreApplication::translate("PicoLoadingScreen", "Waiting for the entity server"));
    _loadingStatusTextures[static_cast<size_t>(LoadingPhase::RECONNECTING_WORLD)] =
        makeLoadingStatusTexture(
            QCoreApplication::translate("PicoLoadingScreen", "Retrying world data"),
            QCoreApplication::translate("PicoLoadingScreen", "Requesting a fresh entity scene"));
    for (int percentage = 0; percentage <= 100; ++percentage) {
        _loadingProgressTextures[percentage] = makeLoadingProgressTexture(percentage);
    }
#endif
}

GraphicsEngine::~GraphicsEngine() {
}

#ifdef USE_GL
void GraphicsEngine::initializeGPU(GLWidget* primaryWidget) {
#else
void GraphicsEngine::initializeGPU(VKWidget* primaryWidget) {
#endif

    _renderEventHandler = new RenderEventHandler(
        [this]() { return this->shouldPaint(); },
        [this]() { this->render_performFrame(); }
    );

    // Requires the window context, because that's what's used in the actual rendering
    // and the GPU backend will make things like the VAO which cannot be shared across
    // contexts
    primaryWidget->makeCurrent();
#ifdef USE_GL
    gpu::Context::init<gpu::gl::GLBackend>();
#else
    gpu::Context::init<gpu::vk::VKBackend>();
#endif
    primaryWidget->makeCurrent();
    _gpuContext = std::make_shared<gpu::Context>();

#if !defined(Q_OS_ANDROID) && !defined(Q_OS_IOS)
    _gpuContext->pushProgramsToSync(shader::startupPrograms(), [this] {
        _programsCompiled.store(true);
    }, 1);
#endif

    DependencyManager::get<TextureCache>()->setGPUContext(_gpuContext);
}

void GraphicsEngine::initializeRender() {

    // Set up the render engine
    render::CullFunctor cullFunctor = LODManager::shouldRender;
    _renderEngine->addJob<UpdateSceneTask>("UpdateScene");
#ifndef Q_OS_ANDROID
    _renderEngine->addJob<SecondaryCameraRenderTask>("SecondaryCameraJob", cullFunctor);
#endif
    _renderEngine->addJob<RenderViewTask>("RenderMainView", cullFunctor, render::ItemKey::TAG_BITS_0, render::ItemKey::TAG_BITS_0);
    _renderEngine->load();
    _renderEngine->registerScene(_renderScene);

    // Now that OpenGL is initialized, we are sure we have a valid context and can create the various pipeline shaders with success.
    DependencyManager::get<GeometryCache>()->initializeShapePipelines();

#if defined(ANDROID_APP_PICO_INTERFACE)
    auto geometryCache = DependencyManager::get<GeometryCache>();
    _loadingBackgroundGeometry = geometryCache->allocateID();
    _loadingLogoGeometry = geometryCache->allocateID();
    _loadingStatusGeometry = geometryCache->allocateID();
    _loadingProgressTextGeometry = geometryCache->allocateID();
    _loadingTrackGeometry = geometryCache->allocateID();
    _loadingProgressGeometry = geometryCache->allocateID();
#endif
}

void GraphicsEngine::startup() {
    static_cast<RenderEventHandler*>(_renderEventHandler)->resumeThread();
}

void GraphicsEngine::shutdown() {
    // The cleanup process enqueues the transactions but does not process them.  Calling this here will force the actual
    // removal of the items.
    // See https://highfidelity.fogbugz.com/f/cases/5328
    _renderScene->enqueueFrame(); // flush all the transactions
    _renderScene->processTransactionQueue(); // process and apply deletions

    _gpuContext->shutdown();

#if defined(ANDROID_APP_PICO_INTERFACE)
    auto geometryCache = DependencyManager::get<GeometryCache>();
    if (geometryCache) {
        geometryCache->releaseID(_loadingBackgroundGeometry);
        geometryCache->releaseID(_loadingLogoGeometry);
        geometryCache->releaseID(_loadingStatusGeometry);
        geometryCache->releaseID(_loadingProgressTextGeometry);
        geometryCache->releaseID(_loadingTrackGeometry);
        geometryCache->releaseID(_loadingProgressGeometry);
    }
#endif


    // shutdown render engine
    _renderScene = nullptr;
    _renderEngine = nullptr;

    _renderEventHandler->deleteLater();
}


void GraphicsEngine::render_runRenderFrame(RenderArgs* renderArgs) {
    PROFILE_RANGE(render, __FUNCTION__);
    PerformanceTimer perfTimer("render");

    // Make sure the WorldBox is in the scene
    // For the record, this one RenderItem is the first one we created and added to the scene.
    // We could move that code elsewhere but you know...
    if (!render::Item::isValidID(WorldBoxRenderData::_item)) {
        render::Transaction transaction;
        auto worldBoxRenderData = std::make_shared<WorldBoxRenderData>();
        auto worldBoxRenderPayload = std::make_shared<WorldBoxRenderData::Payload>(worldBoxRenderData);

        WorldBoxRenderData::_item = _renderScene->allocateID();

        transaction.resetItem(WorldBoxRenderData::_item, worldBoxRenderPayload);
        _renderScene->enqueueTransaction(transaction);
    }

    {
        _renderEngine->getRenderContext()->args = renderArgs;
        _renderEngine->run();
    }
}

static const unsigned int THROTTLED_SIM_FRAMERATE = 15;
static const int THROTTLED_SIM_FRAME_PERIOD_MS = MSECS_PER_SECOND / THROTTLED_SIM_FRAMERATE;

bool GraphicsEngine::shouldPaint() const {
    auto displayPlugin = qApp->getActiveDisplayPlugin();
    if (!displayPlugin) {
        // We're shutting down
        return false;
    }

#ifdef DEBUG_PAINT_DELAY
        static uint64_t paintDelaySamples{ 0 };
        static uint64_t paintDelayUsecs{ 0 };

        paintDelayUsecs += displayPlugin->getPaintDelayUsecs();

        static const int PAINT_DELAY_THROTTLE = 1000;
        if (++paintDelaySamples % PAINT_DELAY_THROTTLE == 0) {
            qCDebug(interfaceapp).nospace() <<
                "Paint delay (" << paintDelaySamples << " samples): " <<
                (float)paintDelaySamples / paintDelayUsecs << "us";
        }
#endif

    // Throttle if requested
    //if (displayPlugin->isThrottled() && (_graphicsEngine._renderEventHandler->_lastTimeRendered.elapsed() < THROTTLED_SIM_FRAME_PERIOD_MS)) {
    //TODO: this may be obsolete? Isn't framerate managed in a different way now?
    if (displayPlugin->isThrottled() &&
            (static_cast<RenderEventHandler*>(_renderEventHandler)->_lastTimeRendered.elapsed() < THROTTLED_SIM_FRAME_PERIOD_MS)) {
        return false;
    }

    return true;
}

bool GraphicsEngine::checkPendingRenderEvent() {
    bool expected = false;
    return (_renderEventHandler && static_cast<RenderEventHandler*>(_renderEventHandler)->_pendingRenderEvent.compare_exchange_strong(expected, true));
}

void GraphicsEngine::render_performFrame() {
    // Some plugins process message events, allowing paintGL to be called reentrantly.

    _renderFrameCount++;

    auto lastPaintBegin = usecTimestampNow();
    PROFILE_RANGE_EX(render, __FUNCTION__, 0xff0000ff, (uint64_t)_renderFrameCount);
    PerformanceTimer perfTimer("paintGL");

    DisplayPluginPointer displayPlugin;
    {
        PROFILE_RANGE(render, "/getActiveDisplayPlugin");
        displayPlugin = qApp->getActiveDisplayPlugin();
        if (!displayPlugin) {
            // We're shutting down
            return;
        }
    }

    {
        PROFILE_RANGE(render, "/pluginBeginFrameRender");
        // If a display plugin loses its underlying support, it
        // needs to be able to signal us to not use it
        if (!displayPlugin->beginFrameRender(_renderFrameCount)) {
            QMetaObject::invokeMethod(qApp, "updateDisplayMode");
            return;
        }
    }

    RenderArgs renderArgs;
    glm::mat4  HMDSensorPose;
    glm::mat4  eyeToWorld;
    glm::mat4  sensorToWorld;
    ViewFrustum viewFrustum;

    bool isStereo;
    glm::mat4  stereoEyeOffsets[2];
    glm::mat4  stereoEyeProjections[2];

    {
        QMutexLocker viewLocker(&_renderArgsMutex);
        renderArgs = _appRenderArgs._renderArgs;

        // don't render if there is no context.
        if (!_appRenderArgs._renderArgs._context) {
            return;
        }

        HMDSensorPose = _appRenderArgs._headPose;
        eyeToWorld = _appRenderArgs._eyeToWorld;
        sensorToWorld = _appRenderArgs._sensorToWorld;
        isStereo = _appRenderArgs._isStereo;
        for_each_eye([&](Eye eye) {
            stereoEyeOffsets[eye] = _appRenderArgs._eyeOffsets[eye];
            stereoEyeProjections[eye] = _appRenderArgs._eyeProjections[eye];
        });
        viewFrustum = _appRenderArgs._renderArgs.getViewFrustum();
    }

    {
        PROFILE_RANGE(render, "/gpuContextReset");
        getGPUContext()->beginFrame(_appRenderArgs._view, HMDSensorPose);
        // Reset the gpu::Context Stages
        // Back to the default framebuffer;
        gpu::doInBatch("Application_render::gpuContextReset", getGPUContext(), [&](gpu::Batch& batch) {
            batch.resetStages();
        });

        if (isStereo) {
            renderArgs._context->enableStereo(true);
            renderArgs._context->setStereoProjections(stereoEyeProjections);
            renderArgs._context->setStereoViews(stereoEyeOffsets);
        }
    }

    gpu::FramebufferPointer finalFramebuffer;
    QSize finalFramebufferSize;
    {
        PROFILE_RANGE(render, "/getOutputFramebuffer");
        // Primary rendering pass
        auto framebufferCache = DependencyManager::get<FramebufferCache>();
        finalFramebufferSize = framebufferCache->getFrameBufferSize();
        // Final framebuffer that will be handed to the display-plugin
        finalFramebuffer = framebufferCache->getFramebuffer();
    }

    std::queue<Application::SnapshotOperator> snapshotOperators;
    if (!_programsCompiled.load()) {
        if (_texture->isLoaded()) {
            gpu::doInBatch("splashFrame", _gpuContext, [&](gpu::Batch& batch) {
                batch.setFramebuffer(finalFramebuffer);
                batch.enableSkybox(true);
                batch.enableStereo(isStereo);
                batch.clearDepthStencilFramebuffer(1.0, 0);
                batch.setViewportTransform({ 0, 0, finalFramebuffer->getSize() });
                batch.setResourceTexture(0, _texture->getGPUTexture());
                _splashScreen->render(batch, viewFrustum, renderArgs._renderMethod == RenderArgs::RenderMethod::FORWARD, render::RenderEngine::TS_BACKGROUND_VIEW);
            });
        }
    } else {
        {
            PROFILE_RANGE(render, "/renderOverlay");
            PerformanceTimer perfTimer("renderOverlay");
            // NOTE: There is no batch associated with this renderArgs
            // the ApplicationOverlay class assumes its viewport is set up to be the device size
            renderArgs._viewport = glm::ivec4(0, 0, qApp->getDeviceSize());
            qApp->getApplicationOverlay().renderOverlay(&renderArgs);
        }

        {
            PROFILE_RANGE(render, "/updateCompositor");
            qApp->getApplicationCompositor().setFrameInfo(_renderFrameCount, eyeToWorld, sensorToWorld);
        }

        {
            PROFILE_RANGE(render, "/runRenderFrame");
            renderArgs._hudOperator = qApp->getApplicationOverlay().enabled() ? displayPlugin->getHUDOperator() : nullptr;
            renderArgs._hudTexture = qApp->getApplicationOverlay().getOverlayTexture();
            renderArgs._takingSnapshot = qApp->takeSnapshotOperators(snapshotOperators);
            renderArgs._blitFramebuffer = finalFramebuffer;
            render_runRenderFrame(&renderArgs);
        }
    }

#if defined(ANDROID_APP_PICO_INTERFACE)
    if (_loadingVisible.load(std::memory_order_acquire)) {
        renderLoadingFrame(finalFramebuffer, isStereo);
    }
#endif

    auto frame = getGPUContext()->endFrame();
    frame->frameIndex = _renderFrameCount;
    frame->framebuffer = finalFramebuffer;
    frame->framebufferRecycler = [](const gpu::FramebufferPointer& framebuffer) {
        auto frameBufferCache = DependencyManager::get<FramebufferCache>();
        if (frameBufferCache) {
            frameBufferCache->releaseFramebuffer(framebuffer);
        }
    };
    frame->snapshotOperators = snapshotOperators;
    // deliver final scene rendering commands to the display plugin
    {
        PROFILE_RANGE(render, "/pluginOutput");
        PerformanceTimer perfTimer("pluginOutput");
        _renderLoopCounter.increment();
        displayPlugin->submitFrame(frame);
    }

    // Reset the framebuffer and stereo state
    renderArgs._blitFramebuffer.reset();
    renderArgs._context->enableStereo(false);

#if !defined(DISABLE_QML)
    {
        auto stats = Stats::getInstance();
        if (stats) {
            stats->setRenderDetails(renderArgs._details);
        }
    }
#endif

    uint64_t lastPaintDuration = usecTimestampNow() - lastPaintBegin;
    _frameTimingsScriptingInterface.addValue(lastPaintDuration);
}

void GraphicsEngine::editRenderArgs(RenderArgsEditor editor) {
    QMutexLocker renderLocker(&_renderArgsMutex);
    editor(_appRenderArgs);
}

#if defined(ANDROID_APP_PICO_INTERFACE)
gpu::TexturePointer GraphicsEngine::makeLoadingStatusTexture(const QString& title, const QString& detail) const {
    constexpr int WIDTH = 1024;
    constexpr int HEIGHT = 160;
    QImage image(WIDTH, HEIGHT, QImage::Format_RGBA8888);
    image.fill(Qt::transparent);

    QPainter painter(&image);
    painter.setRenderHint(QPainter::Antialiasing);
    painter.setRenderHint(QPainter::TextAntialiasing);
    QFont font = painter.font();
    font.setPixelSize(64);
    font.setWeight(QFont::DemiBold);
    painter.setFont(font);
    painter.setPen(QColor(240, 245, 250));
    painter.drawText(QRect(0, 0, WIDTH, 94), Qt::AlignHCenter | Qt::AlignBottom, title);
    font.setPixelSize(42);
    font.setWeight(QFont::Normal);
    painter.setFont(font);
    painter.setPen(QColor(190, 202, 215));
    painter.drawText(QRect(0, 98, WIDTH, 52), Qt::AlignHCenter | Qt::AlignTop, detail);
    painter.end();

    auto texture = gpu::Texture::create2D(
        gpu::Element(gpu::VEC4, gpu::NUINT8, gpu::RGBA), WIDTH, HEIGHT,
        gpu::Texture::SINGLE_MIP, Sampler(Sampler::FILTER_MIN_MAG_LINEAR, Sampler::WRAP_CLAMP));
    texture->setStoredMipFormat(gpu::Element(gpu::VEC4, gpu::NUINT8, gpu::RGBA));
    texture->assignStoredMip(0, image.sizeInBytes(), image.constBits());
    texture->setImportant(true);
    return texture;
}

gpu::TexturePointer GraphicsEngine::makeLoadingProgressTexture(int percentage) const {
    constexpr int WIDTH = 256;
    constexpr int HEIGHT = 96;
    QImage image(WIDTH, HEIGHT, QImage::Format_RGBA8888);
    image.fill(Qt::transparent);

    QPainter painter(&image);
    painter.setRenderHint(QPainter::Antialiasing);
    painter.setRenderHint(QPainter::TextAntialiasing);
    QFont font = painter.font();
    font.setPixelSize(64);
    font.setWeight(QFont::DemiBold);
    painter.setFont(font);
    painter.setPen(QColor(210, 219, 229));
    painter.drawText(image.rect(), Qt::AlignCenter, QString::number(percentage) + QLatin1Char('%'));
    painter.end();

    auto texture = gpu::Texture::create2D(
        gpu::Element(gpu::VEC4, gpu::NUINT8, gpu::RGBA), WIDTH, HEIGHT,
        gpu::Texture::SINGLE_MIP, Sampler(Sampler::FILTER_MIN_MAG_LINEAR, Sampler::WRAP_CLAMP));
    texture->setStoredMipFormat(gpu::Element(gpu::VEC4, gpu::NUINT8, gpu::RGBA));
    texture->assignStoredMip(0, image.sizeInBytes(), image.constBits());
    texture->setImportant(true);
    return texture;
}

void GraphicsEngine::setLoadingState(bool visible, LoadingPhase phase, float progress) {
    _loadingPhase.store(phase, std::memory_order_relaxed);
    _loadingProgress.store(glm::clamp(progress, 0.0f, 1.0f), std::memory_order_relaxed);
    _loadingVisible.store(visible, std::memory_order_release);
}

void GraphicsEngine::renderLoadingFrame(const gpu::FramebufferPointer& framebuffer, bool isStereo) {
    if (!framebuffer) {
        return;
    }

    auto geometryCache = DependencyManager::get<GeometryCache>();
    auto textureCache = DependencyManager::get<TextureCache>();
    const glm::uvec2 framebufferSize = framebuffer->getSize();
    const int eyeCount = isStereo ? 2 : 1;
    const int eyeWidth = static_cast<int>(framebufferSize.x) / eyeCount;
    const int eyeHeight = static_cast<int>(framebufferSize.y);
    const float eyeAspect = eyeHeight > 0 ? static_cast<float>(eyeWidth) / eyeHeight : 1.0f;
    constexpr float LOADING_UI_SCALE = 0.25f;
    const float logoWidth = 1.18f * LOADING_UI_SCALE;
    const float logoHeight = logoWidth * eyeAspect * (130.60057f / 497.41665f);
    const auto phase = _loadingPhase.load(std::memory_order_relaxed);
    const float statusWidth = 1.35f * LOADING_UI_SCALE;
    const float statusHeight = statusWidth * eyeAspect * (160.0f / 1024.0f);
    const float progress = _loadingProgress.load(std::memory_order_relaxed);
    const int progressPercentage = glm::clamp(static_cast<int>(std::round(progress * 100.0f)), 0, 100);

    gpu::doInBatch("PicoLoadingFrame", _gpuContext, [&](gpu::Batch& batch) {
        batch.setFramebuffer(framebuffer);
        batch.enableStereo(false);
        batch.setProjectionTransform(glm::mat4(1.0f));
        batch.setModelTransform(Transform());
        batch.resetViewTransform();
        geometryCache->useSimpleDrawPipeline(batch);

        for (int eye = 0; eye < eyeCount; ++eye) {
            batch.setViewportTransform({ eye * eyeWidth, 0, eyeWidth, eyeHeight });

            batch.setResourceTexture(0, textureCache->getWhiteTexture());
            geometryCache->renderUnitQuad(batch, glm::vec4(0.018f, 0.035f, 0.060f, 1.0f),
                                          _loadingBackgroundGeometry);

            if (_loadingLogo && _loadingLogo->isLoaded()) {
                batch.setResourceTexture(0, _loadingLogo->getGPUTexture());
                geometryCache->renderQuad(
                    batch,
                    glm::vec2(-0.5f * logoWidth, 0.24f * LOADING_UI_SCALE - 0.5f * logoHeight),
                    glm::vec2(0.5f * logoWidth, 0.24f * LOADING_UI_SCALE + 0.5f * logoHeight),
                    glm::vec2(0.0f, 1.0f), glm::vec2(1.0f, 0.0f), glm::vec4(1.0f),
                    _loadingLogoGeometry);
            }

            const size_t phaseIndex = static_cast<size_t>(phase);
            if (phaseIndex < _loadingStatusTextures.size() && _loadingStatusTextures[phaseIndex]) {
                batch.setResourceTexture(0, _loadingStatusTextures[phaseIndex]);
                geometryCache->renderQuad(
                    batch,
                    glm::vec2(-0.5f * statusWidth, -0.18f * LOADING_UI_SCALE - 0.5f * statusHeight),
                    glm::vec2(0.5f * statusWidth, -0.18f * LOADING_UI_SCALE + 0.5f * statusHeight),
                    glm::vec2(0.0f, 1.0f), glm::vec2(1.0f, 0.0f), glm::vec4(1.0f),
                    _loadingStatusGeometry);
            }

            constexpr float TRACK_WIDTH = 1.10f * LOADING_UI_SCALE;
            constexpr float TRACK_HEIGHT = 0.035f * LOADING_UI_SCALE;
            constexpr float TRACK_Y = -0.40f * LOADING_UI_SCALE;
            batch.setResourceTexture(0, textureCache->getWhiteTexture());
            geometryCache->renderQuad(
                batch,
                glm::vec2(-0.5f * TRACK_WIDTH, TRACK_Y - 0.5f * TRACK_HEIGHT),
                glm::vec2(0.5f * TRACK_WIDTH, TRACK_Y + 0.5f * TRACK_HEIGHT),
                glm::vec4(0.10f, 0.16f, 0.23f, 1.0f), _loadingTrackGeometry);
            geometryCache->renderQuad(
                batch,
                glm::vec2(-0.5f * TRACK_WIDTH, TRACK_Y - 0.5f * TRACK_HEIGHT),
                glm::vec2(-0.5f * TRACK_WIDTH + TRACK_WIDTH * progress,
                          TRACK_Y + 0.5f * TRACK_HEIGHT),
                glm::vec4(0.40f, 0.40f, 0.67f, 1.0f), _loadingProgressGeometry);

            constexpr float PROGRESS_TEXT_WIDTH = 0.34f * LOADING_UI_SCALE;
            const float progressTextHeight = PROGRESS_TEXT_WIDTH * eyeAspect * (96.0f / 256.0f);
            constexpr float PROGRESS_TEXT_Y = -0.53f * LOADING_UI_SCALE;
            batch.setResourceTexture(0, _loadingProgressTextures[progressPercentage]);
            geometryCache->renderQuad(
                batch,
                glm::vec2(-0.5f * PROGRESS_TEXT_WIDTH, PROGRESS_TEXT_Y - 0.5f * progressTextHeight),
                glm::vec2(0.5f * PROGRESS_TEXT_WIDTH, PROGRESS_TEXT_Y + 0.5f * progressTextHeight),
                glm::vec2(0.0f, 1.0f), glm::vec2(1.0f, 0.0f), glm::vec4(1.0f),
                _loadingProgressTextGeometry);
        }

        batch.setResourceTexture(0, nullptr);
    });
}
#endif
