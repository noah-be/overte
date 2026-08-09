//
// Overte OpenXR Plugin
//
// Copyright 2024 Lubosz Sarnecki
// Copyright 2024 Overte e.V.
//
// SPDX-License-Identifier: Apache-2.0
//

#include "OpenXrDisplayPlugin.h"
#include "OpenXrDisplayPolicy.h"
#include <qloggingcategory.h>
#include <SettingHandle.h>

#include "ViewFrustum.h"

#include <chrono>
#include <glm/gtx/string_cast.hpp>
#include <glm/gtx/transform.hpp>
#include <thread>
#include <sstream>
#include <utility>

#if defined(Q_OS_ANDROID)
#include <sys/system_properties.h>
#endif

#if defined(Q_OS_WIN)
#undef near
#undef far
#endif

Q_DECLARE_LOGGING_CATEGORY(xr_display_cat)
Q_LOGGING_CATEGORY(xr_display_cat, "openxr.display")

constexpr GLint XR_PREFERRED_COLOR_FORMAT = GL_SRGB8_ALPHA8;

static uint32_t scaledEyeDimension(uint32_t recommended) {
#if defined(Q_OS_ANDROID)
    // Swapchain dimensions cannot safely be changed while an OpenXR session
    // is active. Read overrides only when the session starts. The ADB property
    // takes precedence for controlled tests, followed by the persistent tablet
    // setting and the measured Pico 4 quality/performance knee of 80%.
    static const float renderScale = [] {
        Setting::Handle<float> renderScaleSetting("pico/renderScale", 0.0f);
        float scale { 0.0f };
        char value[PROP_VALUE_MAX] {};
        if (__system_property_get("debug.overte.render_scale", value) > 0) {
            bool ok { false };
            const float requested = QString::fromLatin1(value).toFloat(&ok);
            if (ok) {
                scale = requested;
            }
        }
        if (scale <= 0.0f) {
            scale = renderScaleSetting.get();
        }
        if (scale <= 0.0f) {
            scale = 0.80f;
        }
        scale = std::max(0.50f, std::min(scale, 1.0f));
        qCInfo(xr_display_cat) << "PICO_RENDER_SCALE" << scale;
        return scale;
    }();
    return std::max(1u, static_cast<uint32_t>(recommended * renderScale));
#else
    return recommended;
#endif
}

#if defined(Q_OS_ANDROID)
static XrFoveationLevelFB picoFoveationLevel() {
    // Keep this as a process-start setting because OpenXR swapchain foveation
    // is configured when the display session is initialized. The adb property
    // makes repeatable A/B power tests possible without changing Pico settings.
    char value[PROP_VALUE_MAX] {};
    if (__system_property_get("debug.overte.foveation", value) <= 0) {
        // Keep the experimental path available for later A/B tests, but do
        // not silently enable it in normal builds. The first Pico power run
        // did not show an efficiency benefit from LOW foveation.
        return XR_FOVEATION_LEVEL_NONE_FB;
    }

    const QString requested = QString::fromLatin1(value).trimmed().toLower();
    if (requested == "0" || requested == "off" || requested == "none") {
        return XR_FOVEATION_LEVEL_NONE_FB;
    }
    if (requested == "2" || requested == "medium") {
        return XR_FOVEATION_LEVEL_MEDIUM_FB;
    }
    if (requested == "3" || requested == "high") {
        return XR_FOVEATION_LEVEL_HIGH_FB;
    }
    return XR_FOVEATION_LEVEL_LOW_FB;
}
#endif

OpenXrDisplayPlugin::OpenXrDisplayPlugin(std::shared_ptr<OpenXrContext> c) {
    _context = c;
}

bool OpenXrDisplayPlugin::isSupported() const {
    return _context->_isValid && _context->_isSupported;
}

inline static glm::mat4 fovToProjection(const XrFovf fov, const float near, const float far) {
    const float left = tanf(fov.angleLeft);
    const float right = tanf(fov.angleRight);
    const float down = tanf(fov.angleDown);
    const float up = tanf(fov.angleUp);

    const float width = right - left;
    const float height = up - down;

    const float m11 = 2 / width;
    const float m22 = 2 / height;
    const float m33 = -(far + near) / (far - near);

    const float m31 = (right + left) / width;
    const float m32 = (up + down) / height;
    const float m43 = -(far * (near + near)) / (far - near);

    // clang-format off
    const float mat[16] = {
        m11, 0  , 0  ,  0,
        0  , m22, 0  ,  0,
        m31, m32, m33, -1,
        0  , 0  , m43,  0,
    };
    // clang-format on

    return glm::make_mat4(mat);
}

glm::mat4 OpenXrDisplayPlugin::getEyeProjection(Eye eye, const glm::mat4& baseProjection) const {
    if (!_views.has_value()) {
        return baseProjection;
    }

    ViewFrustum frustum;
    frustum.setProjection(baseProjection);
    return fovToProjection(_views.value()[(eye == Left) ? 0 : 1].fov, frustum.getNearClip(), frustum.getFarClip());
}

// TODO: interface/src/Application_Graphics.cpp:535
glm::mat4 OpenXrDisplayPlugin::getCullingProjection(const glm::mat4& baseProjection) const {
    if (!_views.has_value()) {
        return baseProjection;
    }

    ViewFrustum frustum;
    frustum.setProjection(baseProjection);

    std::array<XrFovf, 2> fovs = { _views.value()[0].fov, _views.value()[1].fov };

    const float maxAngle = 0.9f * PI / 2;
    const float margin = 1.1f;

    XrFovf fovMax;
    fovMax.angleDown = std::clamp(std::min(fovs[0].angleDown, fovs[1].angleDown) * margin, -maxAngle, maxAngle);
    fovMax.angleLeft = std::clamp(std::min(fovs[0].angleLeft, fovs[1].angleLeft) * margin, -maxAngle, maxAngle);
    fovMax.angleRight = std::clamp(std::max(fovs[0].angleRight, fovs[1].angleRight) * margin, -maxAngle, maxAngle);
    fovMax.angleUp = std::clamp(std::max(fovs[0].angleUp, fovs[1].angleUp) * margin, -maxAngle, maxAngle);

    return fovToProjection(fovMax, frustum.getNearClip(), frustum.getFarClip());
}

float OpenXrDisplayPlugin::getTargetFrameRate() const {
#if defined(Q_OS_ANDROID)
    // Pico 4's lowest native display mode is 72 Hz. Keeping rendering and
    // presentation synchronized avoids the uneven cadence of 60 FPS on 72 Hz.
    return 72.0f;
#else
    // predictedDisplayPeriod is delta nanoseconds, so convert it to frames per second
    return std::max(1.0f, 1.0f / (_lastFrameState.predictedDisplayPeriod / 1e9f));
#endif
}

bool OpenXrDisplayPlugin::initViews() {
    XrInstance instance = _context->_instance;
    XrSystemId systemId = _context->_systemId;

    uint32_t reportedViewCount = 0;
    XrResult result = xrEnumerateViewConfigurationViews(
        instance, systemId, XR_VIEW_CONFIG_TYPE, 0, &reportedViewCount, nullptr);
    if (!xrCheck(instance, result, "Failed to get view configuration view count!")) {
        qCCritical(xr_display_cat, "Failed to get view configuration view count!");
        return false;
    }

    if (!isSupportedOpenXrViewCount(reportedViewCount)) {
        qCCritical(xr_display_cat, "Runtime reported unsupported view count: %u", reportedViewCount);
        return false;
    }

    std::vector<XrView> views;
    std::vector<XrViewConfigurationView> viewConfigs;
    for (uint32_t i = 0; i < reportedViewCount; i++) {
        XrView view = { .type = XR_TYPE_VIEW };
        views.push_back(view);

        XrViewConfigurationView viewConfig = { .type = XR_TYPE_VIEW_CONFIGURATION_VIEW };
        viewConfigs.push_back(viewConfig);
    }

    uint32_t enumeratedViewCount = reportedViewCount;
    result = xrEnumerateViewConfigurationViews(
        instance, systemId, XR_VIEW_CONFIG_TYPE, reportedViewCount,
        &enumeratedViewCount, viewConfigs.data());
    if (!xrCheck(instance, result, "Failed to enumerate view configuration views!")) {
        qCCritical(xr_display_cat, "Failed to enumerate view configuration views!");
        return false;
    }
    if (!isSupportedOpenXrViewCount(enumeratedViewCount)) {
        qCCritical(xr_display_cat, "Runtime enumerated unsupported view count: %u", enumeratedViewCount);
        return false;
    }

    _viewCount = enumeratedViewCount;
    _views = std::move(views);
    _viewConfigs = std::move(viewConfigs);
    _swapChains.resize(_viewCount);
    _swapChainLengths.resize(_viewCount);
    _swapChainIndices.resize(_viewCount);
    _images.resize(_viewCount);

    return true;
}

#define ENUM_TO_STR(r) \
    case r:            \
        return #r

static std::string glFormatStr(GLenum source) {
    switch (source) {
        ENUM_TO_STR(GL_RGBA16);
        ENUM_TO_STR(GL_RGBA16F);
        ENUM_TO_STR(GL_SRGB8_ALPHA8);
        ENUM_TO_STR(GL_RGB10_A2UI);
        default: {
            std::stringstream stream;
            stream << "0x" << std::uppercase << std::hex << source;
            return stream.str();
        }
    }
}

static int64_t chooseSwapChainFormat(XrInstance instance, XrSession session, int64_t preferred) {
    uint32_t formatCount;
    XrResult result = xrEnumerateSwapchainFormats(session, 0, &formatCount, nullptr);
    if (!xrCheck(instance, result, "Failed to get number of supported swapchain formats"))
        return -1;

    qCInfo(xr_display_cat, "Runtime supports %d swapchain formats", formatCount);
    std::vector<int64_t> formats(formatCount);

    result = xrEnumerateSwapchainFormats(session, formatCount, &formatCount, formats.data());
    if (!xrCheck(instance, result, "Failed to enumerate swapchain formats"))
        return -1;

    for (uint32_t i = 0; i < formatCount; i++) {
        qCInfo(xr_display_cat, "Supported GL format: %s", glFormatStr(formats[i]).c_str());
    }
    const int64_t chosen = selectOpenXrSwapchainFormat(formats.data(), formatCount, preferred);
    if (chosen == OPENXR_NO_SWAPCHAIN_FORMAT) {
        qCCritical(xr_display_cat, "Runtime returned no usable swapchain formats");
        return OPENXR_NO_SWAPCHAIN_FORMAT;
    }
    if (chosen == preferred) {
        qCInfo(xr_display_cat, "Using preferred swapchain format %s", glFormatStr(chosen).c_str());
    }
    if (chosen != preferred) {
        qCWarning(xr_display_cat, "Falling back to non preferred swapchain format %s", glFormatStr(chosen).c_str());
    }

    return chosen;
}

bool OpenXrDisplayPlugin::initSwapChains() {
    XrInstance instance = _context->_instance;
    XrSession session = _context->_session;
    destroySwapChains();
    auto failInitialization = [this] {
        destroySwapChains();
        return false;
    };

    int64_t format = chooseSwapChainFormat(instance, session, XR_PREFERRED_COLOR_FORMAT);
    if (format == OPENXR_NO_SWAPCHAIN_FORMAT) {
        return failInitialization();
    }

#if defined(Q_OS_ANDROID)
    const XrFoveationLevelFB foveationLevel = picoFoveationLevel();
    const bool enableFoveation = _context->_foveationSupported && foveationLevel != XR_FOVEATION_LEVEL_NONE_FB;
    XrSwapchainCreateInfoFoveationFB foveationSwapchainInfo = {
        .type = XR_TYPE_SWAPCHAIN_CREATE_INFO_FOVEATION_FB,
        .next = nullptr,
        .flags = XR_SWAPCHAIN_CREATE_FOVEATION_SCALED_BIN_BIT_FB,
    };
#endif

    for (uint32_t i = 0; i < _viewCount; i++) {
        _images[i].clear();

        XrSwapchainCreateInfo info = {
            .type = XR_TYPE_SWAPCHAIN_CREATE_INFO,
#if defined(Q_OS_ANDROID)
            .next = enableFoveation ? &foveationSwapchainInfo : nullptr,
#endif
            .createFlags = 0,
            .usageFlags = XR_SWAPCHAIN_USAGE_SAMPLED_BIT | XR_SWAPCHAIN_USAGE_COLOR_ATTACHMENT_BIT,
            .format = format,
            .sampleCount = _viewConfigs[i].recommendedSwapchainSampleCount,
            .width = scaledEyeDimension(_viewConfigs[i].recommendedImageRectWidth),
            .height = scaledEyeDimension(_viewConfigs[i].recommendedImageRectHeight),
            .faceCount = 1,
            .arraySize = 1,
            .mipCount = 1,
        };

        XrResult result = xrCreateSwapchain(session, &info, &_swapChains[i]);
        if (!xrCheck(instance, result, "Failed to create swapchain!"))
            return failInitialization();

        uint32_t imageCapacity = 0;
        result = xrEnumerateSwapchainImages(_swapChains[i], 0, &imageCapacity, nullptr);
        if (!xrCheck(instance, result, "Failed to enumerate swapchains"))
            return failInitialization();
        if (!isConsistentOpenXrEnumerationCount(imageCapacity, imageCapacity)) {
            qCCritical(xr_display_cat, "Runtime returned no swapchain images for eye %u", i);
            return failInitialization();
        }

        for (uint32_t j = 0; j < imageCapacity; j++) {
            XrSwapchainImageOpenGLKHR image = { .type = XR_TYPE_SWAPCHAIN_IMAGE_OPENGL_KHR };
            _images[i].push_back(image);
        }
        uint32_t returnedImageCount = imageCapacity;
        result = xrEnumerateSwapchainImages(
            _swapChains[i], imageCapacity, &returnedImageCount,
            (XrSwapchainImageBaseHeader*)_images[i].data());
        if (!xrCheck(instance, result, "Failed to enumerate swapchain images"))
            return failInitialization();
        if (!isConsistentOpenXrEnumerationCount(imageCapacity, returnedImageCount)) {
            qCCritical(xr_display_cat,
                       "Runtime returned inconsistent swapchain image count for eye %u: %u of %u",
                       i, returnedImageCount, imageCapacity);
            return failInitialization();
        }
        _images[i].resize(returnedImageCount);
        _swapChainLengths[i] = returnedImageCount;
    }

#if defined(Q_OS_ANDROID)
    if (enableFoveation) {
        XrFoveationLevelProfileCreateInfoFB levelInfo = {
            .type = XR_TYPE_FOVEATION_LEVEL_PROFILE_CREATE_INFO_FB,
            .next = nullptr,
            .level = foveationLevel,
            .verticalOffset = 0.0f,
            .dynamic = XR_FOVEATION_DYNAMIC_DISABLED_FB,
        };
        XrFoveationProfileCreateInfoFB profileInfo = {
            .type = XR_TYPE_FOVEATION_PROFILE_CREATE_INFO_FB,
            .next = &levelInfo,
        };
        XrResult result = _context->xrCreateFoveationProfileFB(session, &profileInfo, &_foveationProfile);
        const bool profileCreated = xrCheck(
            instance, result, "Failed to create foveation profile");
        if (!isOpenXrFoveationProfileUsable(
                profileCreated, _foveationProfile != XR_NULL_HANDLE)) {
            if (profileCreated) {
                qCCritical(xr_display_cat,
                           "OpenXR runtime returned a null foveation profile.");
            }
            return failInitialization();
        }

        XrSwapchainStateFoveationFB state = {
            .type = XR_TYPE_SWAPCHAIN_STATE_FOVEATION_FB,
            .next = nullptr,
            .flags = 0,
            .profile = _foveationProfile,
        };
        for (XrSwapchain swapchain : _swapChains) {
            result = _context->xrUpdateSwapchainFB(
                swapchain, reinterpret_cast<const XrSwapchainStateBaseHeaderFB*>(&state));
            if (!xrCheck(instance, result, "Failed to apply foveation profile")) {
                return failInitialization();
            }
        }
    }
    qCInfo(xr_display_cat) << "PICO_FOVEATION_LEVEL" << static_cast<int>(foveationLevel)
                           << "active" << (enableFoveation && _foveationProfile != XR_NULL_HANDLE);
#endif

    return true;
}

void OpenXrDisplayPlugin::destroySwapChains() {
#if defined(Q_OS_ANDROID)
    if (_foveationProfile != XR_NULL_HANDLE && _context->xrDestroyFoveationProfileFB) {
        xrCheck(_context->_instance, _context->xrDestroyFoveationProfileFB(_foveationProfile),
                "Failed to destroy foveation profile");
        _foveationProfile = XR_NULL_HANDLE;
    }
#endif
    destroyOpenXrHandles(_swapChains, static_cast<XrSwapchain>(XR_NULL_HANDLE),
                         [this](XrSwapchain swapchain) {
        return xrCheck(_context->_instance, xrDestroySwapchain(swapchain),
                       "Failed to destroy swapchain");
    });
    for (auto& images : _images) {
        images.clear();
    }
    std::fill(_swapChainLengths.begin(), _swapChainLengths.end(), 0);
    std::fill(_swapChainIndices.begin(), _swapChainIndices.end(), 0);
}

bool OpenXrDisplayPlugin::initLayers() {
    _projectionLayerViews.clear();
    for (uint32_t i = 0; i < _viewCount; i++) {
        XrCompositionLayerProjectionView layer = {
            .type = XR_TYPE_COMPOSITION_LAYER_PROJECTION_VIEW,
            .subImage = {
                .swapchain = _swapChains[i],
                .imageRect = {
                    .offset = {
                        .x = 0,
                        .y = 0,
                    },
                    .extent = {
                        .width = (int32_t)scaledEyeDimension(_viewConfigs[i].recommendedImageRectWidth),
                        .height = (int32_t)scaledEyeDimension(_viewConfigs[i].recommendedImageRectHeight),
                    },
                },
                .imageArrayIndex = 0,
            },
        };
        _projectionLayerViews.push_back(layer);
    };

    return true;
}

void OpenXrDisplayPlugin::init() {
    Plugin::init();

    if (!initViews()) {
        qCCritical(xr_display_cat, "View init failed.");
        return;
    }

    for (const XrViewConfigurationView& view : _viewConfigs) {
        assert(view.recommendedImageRectWidth != 0);
        qCDebug(xr_display_cat, "Swapchain dimensions: %dx%d", view.recommendedImageRectWidth, view.recommendedImageRectHeight);
        // TODO: Don't render side-by-side but use multiview (texture arrays). This probably won't work with GL.
        _renderTargetSize.x = scaledEyeDimension(view.recommendedImageRectWidth) * 2;
        _renderTargetSize.y = scaledEyeDimension(view.recommendedImageRectHeight);
    }

    emit deviceConnected(getName());
}

const QString OpenXrDisplayPlugin::getName() const {
    // Keep this in sync with --display=OpenXR. PluginManager resolves preferred
    // displays by exact name, so including the runtime's system name prevents
    // this plugin from ever being selected.
    return QStringLiteral("OpenXR");
}

QString OpenXrDisplayPlugin::getPreferredAudioInDevice() const {
    // Android applies acoustic echo cancellation and noise suppression only to
    // this capture source on Pico 4. An explicitly saved user choice still wins.
    return QStringLiteral("voicecommunication");
}

bool OpenXrDisplayPlugin::internalActivate() {
    if (!_context->_isValid) { return false; }

    _context->reset();
    _context->_isDisplayActive = true;
    return HmdDisplayPlugin::internalActivate();
}

void OpenXrDisplayPlugin::internalDeactivate() {
    _context->_isDisplayActive = false;
    HmdDisplayPlugin::internalDeactivate();
}

void OpenXrDisplayPlugin::customizeContext() {
    gl::initModuleGl();
    HmdDisplayPlugin::customizeContext();

    if (!_context->initPostGraphics()) {
        qCCritical(xr_display_cat, "Post graphics init failed.");
        return;
    }

    if (!initSwapChains()) {
        qCCritical(xr_display_cat, "Swap chain init failed.");
        return;
    }

    if (!initLayers()) {
        qCCritical(xr_display_cat, "Layer init failed.");
        return;
    }

    // Create swap chain images for _compositeFramebuffer
    for (size_t i = 0; i < _swapChainLengths[0]; ++i) {
        gpu::TexturePointer texture =
            gpu::Texture::createRenderBuffer(gpu::Element::COLOR_SRGBA_32, _renderTargetSize.x, _renderTargetSize.y,
                                             gpu::Texture::SINGLE_MIP, Sampler(Sampler::FILTER_MIN_MAG_POINT));
        _compositeSwapChain.push_back(texture);
    }
}

void OpenXrDisplayPlugin::uncustomizeContext() {
    _compositeSwapChain.clear();
    _projectionLayerViews.clear();
    destroySwapChains();
    HmdDisplayPlugin::uncustomizeContext();
}

void OpenXrDisplayPlugin::resetSensors() {
}

bool OpenXrDisplayPlugin::beginFrameRender(uint32_t frameIndex) {
    if (!_context->_isValid) {
        deactivate();
        return false;
    }

    _context->pollEvents();

    if (_context->_shouldQuit) {
        QMetaObject::invokeMethod(qApp, "quit");
        return false;
    }

    if (!_context->_shouldRunFrameCycle) {
        qCWarning(xr_display_cat, "beginFrameRender: Shouldn't run frame cycle. Skipping renderin frame %d", frameIndex);
        return true;
    }

    _currentRenderFrameInfo = FrameInfo();
    _currentRenderFrameInfo.predictedDisplayTime = _lastFrameState.predictedDisplayTime / 1e9;

    withNonPresentThreadLock([&] {
        _currentRenderFrameInfo.renderPose = _context->_lastHeadPose.getMatrix();
        _currentRenderFrameInfo.presentPose = _context->_lastHeadPose.getMatrix();
        _frameInfos[frameIndex] = _currentRenderFrameInfo;
    });

    return HmdDisplayPlugin::beginFrameRender(frameIndex);
}

void OpenXrDisplayPlugin::submitFrame(const gpu::FramePointer& newFrame) {
    OpenGLDisplayPlugin::submitFrame(newFrame);
}

void OpenXrDisplayPlugin::compositeLayers() {
    if (!_context->_shouldRunFrameCycle) {
        return;
    }

    if (_lastFrameState.shouldRender) {
        if (!isOpenXrSwapchainImageIndexValid(
                _swapChainIndices[0], _compositeSwapChain.size())) {
            qCCritical(xr_display_cat, "Invalid composite swapchain image index: %u (count %zu)",
                       _swapChainIndices[0], _compositeSwapChain.size());
            return;
        }
        _compositeFramebuffer->setRenderBuffer(0, _compositeSwapChain[_swapChainIndices[0]]);
        HmdDisplayPlugin::compositeLayers();
    }
}

void OpenXrDisplayPlugin::internalPresent() {
    // OpenXR submits directly to the runtime's swapchains.  The inherited HMD
    // implementation additionally renders a desktop mirror into Qt's Android
    // surface, which is no longer valid once the Pico runtime owns presentation.
    hmdPresent();
}

void OpenXrDisplayPlugin::hmdPresent() {
    if (!_context->_isValid) {
        deactivate();
        return;
    }

    if (!_context->_shouldRunFrameCycle) {
        qCWarning(xr_display_cat, "hmdPresent: Shouldn't run frame cycle. Skipping renderin frame %d",
                  _currentFrame->frameIndex);
        return;
    }

    _lastFrameState = { .type = XR_TYPE_FRAME_STATE };
    XrResult result = xrWaitFrame(_context->_session, nullptr, &_lastFrameState);

    if (!xrCheck(_context->_instance, result, "xrWaitFrame failed"))
        return;

    _context->_lastPredictedDisplayTime = _lastFrameState.predictedDisplayTime;
    _context->_lastPredictedDisplayPeriod = _lastFrameState.predictedDisplayPeriod;

#if defined(Q_OS_ANDROID)
    static uint64_t lastPredictionLog { 0 };
    const uint64_t now = usecTimestampNow();
    if (now - lastPredictionLog >= USECS_PER_SECOND) {
        lastPredictionLog = now;
        qCInfo(xr_display_cat) << "PICO_LATENCY_XR_FRAME predictedDisplayTime(ns)"
                              << _lastFrameState.predictedDisplayTime
                              << "period(ms)"
                              << (_lastFrameState.predictedDisplayPeriod / 1000000.0)
                              << "inputLead(ms)"
                              << ((_context->inputPredictionTime() - _lastFrameState.predictedDisplayTime) / 1000000.0);
    }
#endif

    if (!_context->beginFrame())
        return;

    if (_lastFrameState.shouldRender) {
        // TODO: Use multiview swapchain
        uint32_t acquiredCount = 0;
        auto releaseAcquiredImages = [&] {
            for (uint32_t acquired = 0; acquired < acquiredCount; ++acquired) {
                XrSwapchainImageReleaseInfo releaseInfo = { .type = XR_TYPE_SWAPCHAIN_IMAGE_RELEASE_INFO };
                xrCheck(_context->_instance,
                        xrReleaseSwapchainImage(_swapChains[acquired], &releaseInfo),
                        "failed to release swapchain image!");
            }
            acquiredCount = 0;
        };
        for (uint32_t i = 0; i < 2; i++) {
            XrSwapchainImageAcquireInfo acquireInfo = { .type = XR_TYPE_SWAPCHAIN_IMAGE_ACQUIRE_INFO };

            XrResult result = xrAcquireSwapchainImage(_swapChains[i], &acquireInfo, &_swapChainIndices[i]);
            if (!xrCheck(_context->_instance, result, "failed to acquire swapchain image!")) {
                releaseAcquiredImages();
                endFrame();
                return;
            }
            ++acquiredCount;
            const bool validRuntimeImage = isOpenXrSwapchainImageIndexValid(
                _swapChainIndices[i], _images[i].size());
            const bool validCompositeImage = i != 0 || isOpenXrSwapchainImageIndexValid(
                _swapChainIndices[i], _compositeSwapChain.size());
            if (!validRuntimeImage || !validCompositeImage) {
                qCCritical(xr_display_cat,
                           "Runtime returned invalid swapchain image index for eye %u: %u",
                           i, _swapChainIndices[i]);
                releaseAcquiredImages();
                endFrame();
                return;
            }

            XrSwapchainImageWaitInfo waitInfo = {
                .type = XR_TYPE_SWAPCHAIN_IMAGE_WAIT_INFO,
                .timeout = XR_INFINITE_DURATION,
            };
            result = xrWaitSwapchainImage(_swapChains[i], &waitInfo);
            const bool waitSucceeded = xrCheck(
                _context->_instance, result, "failed to wait for swapchain image!");
            const bool timeoutExpired = result == XR_TIMEOUT_EXPIRED;
            if (!isOpenXrSwapchainImageWaitComplete(
                    waitSucceeded, timeoutExpired)) {
                if (timeoutExpired) {
                    qCWarning(xr_display_cat,
                              "OpenXR swapchain image wait timed out unexpectedly.");
                }
                releaseAcquiredImages();
                endFrame();
                return;
            }
        }

        auto backend = getBackend();
        auto glBackend = std::dynamic_pointer_cast<gpu::gl::GLBackend>(backend);
        Q_ASSERT(glBackend);
        GLuint glTexId = glBackend->getTextureID(_compositeFramebuffer->getRenderBuffer(0));

        glCopyImageSubData(glTexId, GL_TEXTURE_2D, 0, 0, 0, 0, _images[0][_swapChainIndices[0]].image, GL_TEXTURE_2D, 0, 0, 0,
                           0, _renderTargetSize.x / 2, _renderTargetSize.y, 1);

        glCopyImageSubData(glTexId, GL_TEXTURE_2D, 0, _renderTargetSize.x / 2, 0, 0, _images[1][_swapChainIndices[1]].image,
                           GL_TEXTURE_2D, 0, 0, 0, 0, _renderTargetSize.x / 2, _renderTargetSize.y, 1);

        releaseAcquiredImages();
    }

    if (!isOpenXrFramePresentationComplete(endFrame())) {
        return;
    }

    _presentRate.increment();
}

bool OpenXrDisplayPlugin::endFrame() {
    XrCompositionLayerProjection projectionLayer = {
        .type = XR_TYPE_COMPOSITION_LAYER_PROJECTION,
        .layerFlags = 0,
        .space = _context->_stageSpace,
        .viewCount = _viewCount,
        .views = _projectionLayerViews.data(),
    };

    std::vector<const XrCompositionLayerBaseHeader*> layers = {
        (const XrCompositionLayerBaseHeader*)&projectionLayer,
    };

    XrFrameEndInfo info = {
        .type = XR_TYPE_FRAME_END_INFO,
        .displayTime = _lastFrameState.predictedDisplayTime,
        .environmentBlendMode = XR_ENVIRONMENT_BLEND_MODE_OPAQUE,
        .layerCount = (uint32_t)layers.size(),
        .layers = layers.data(),
    };

    constexpr XrViewStateFlags requiredViewFlags =
        XR_VIEW_STATE_POSITION_VALID_BIT |
        XR_VIEW_STATE_ORIENTATION_VALID_BIT;
    if (!isOpenXrViewStateUsable(
            _lastViewState.viewStateFlags, requiredViewFlags)) {
        info.layerCount = 0;
    }

    if (!_lastFrameState.shouldRender) {
        info.layerCount = 0;
    }

    XrResult result = xrEndFrame(_context->_session, &info);
    if (!xrCheck(_context->_instance, result, "failed to end frame!")) {
        return false;
    }

    return true;
}

void OpenXrDisplayPlugin::postPreview() {
}

bool OpenXrDisplayPlugin::isHmdMounted() const {
    return _context->_hmdMounted;
}

void OpenXrDisplayPlugin::updatePresentPose() {
    if (!_context->_isValid) {
        deactivate();
        return;
    }

    if (!_context->_isSessionRunning) { return; }

    if (_lastFrameState.predictedDisplayTime == 0) { return; }

    _context->_lastPredictedDisplayTime = _lastFrameState.predictedDisplayTime;

    auto predictedDisplayTime = _lastFrameState.predictedDisplayTime;

    std::vector<XrView> eye_views(_viewCount);
    for (uint32_t i = 0; i < _viewCount; i++) {
        eye_views[i].type = XR_TYPE_VIEW;
    }

    // TODO: Probably shouldn't call xrLocateViews twice. Use only view space views?
    XrViewLocateInfo eyeViewLocateInfo = {
        .type = XR_TYPE_VIEW_LOCATE_INFO,
        .viewConfigurationType = XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO,
        .displayTime = predictedDisplayTime,
        .space = _context->_viewSpace,
    };

    XrViewState eyeViewState = { .type = XR_TYPE_VIEW_STATE };

    uint32_t locatedEyeViewCount = 0;
    XrResult result = xrLocateViews(
        _context->_session, &eyeViewLocateInfo, &eyeViewState, _viewCount,
        &locatedEyeViewCount, eye_views.data());
    if (!xrCheck(_context->_instance, result, "Could not locate views"))
        return;
    if (!isCompleteOpenXrStereoViewResult(_viewCount, locatedEyeViewCount)) {
        qCWarning(xr_display_cat, "Runtime returned incomplete eye views: %u", locatedEyeViewCount);
        return;
    }
    constexpr XrViewStateFlags requiredViewFlags =
        XR_VIEW_STATE_POSITION_VALID_BIT |
        XR_VIEW_STATE_ORIENTATION_VALID_BIT;
    if (!isOpenXrViewStateUsable(
            eyeViewState.viewStateFlags, requiredViewFlags)) {
        qCWarning(xr_display_cat, "Runtime returned invalid eye-view poses");
        return;
    }

    XrViewState worldViewState = { .type = XR_TYPE_VIEW_STATE };
    std::vector<XrView> worldViews(_viewCount);
    for (auto& view : worldViews) {
        view.type = XR_TYPE_VIEW;
    }

    XrViewLocateInfo viewLocateInfo = {
        .type = XR_TYPE_VIEW_LOCATE_INFO,
        .viewConfigurationType = XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO,
        .displayTime = predictedDisplayTime,
        .space = _context->_stageSpace,
    };

    uint32_t locatedWorldViewCount = 0;
    result = xrLocateViews(
        _context->_session, &viewLocateInfo, &worldViewState, _viewCount,
        &locatedWorldViewCount, worldViews.data());
    if (!xrCheck(_context->_instance, result, "Could not locate views"))
        return;
    if (!isCompleteOpenXrStereoViewResult(_viewCount, locatedWorldViewCount)) {
        qCWarning(xr_display_cat, "Runtime returned incomplete world views: %u", locatedWorldViewCount);
        return;
    }
    if (!isOpenXrViewStateUsable(
            worldViewState.viewStateFlags, requiredViewFlags)) {
        qCWarning(xr_display_cat, "Runtime returned invalid world-view poses");
        return;
    }

    for (uint32_t i = 0; i < 2; i++) {
        vec3 eyePosition = xrVecToGlm(eye_views[i].pose.position);
        quat eyeOrientation = xrQuatToGlm(eye_views[i].pose.orientation);
        _eyeOffsets[i] = controller::Pose(
            eyePosition, eyeOrientation).getMatrix();
    }

    _lastViewState = worldViewState;
    _views.value() = worldViews;

    for (uint32_t i = 0; i < _viewCount; i++) {
        _projectionLayerViews[i].pose = worldViews[i].pose;
        _projectionLayerViews[i].fov = worldViews[i].fov;
    }

    XrSpaceLocation headLocation = {
        .type = XR_TYPE_SPACE_LOCATION,
        .pose = XR_INDENTITY_POSE,
    };
    const bool headLocated = xrCheck(
        _context->_instance,
        xrLocateSpace(
            _context->_viewSpace, _context->_stageSpace,
            predictedDisplayTime, &headLocation),
        "Could not locate head pose");
    constexpr XrSpaceLocationFlags requiredHeadFlags =
        XR_SPACE_LOCATION_POSITION_VALID_BIT |
        XR_SPACE_LOCATION_ORIENTATION_VALID_BIT;
    if (!isOpenXrLocatedPoseUsable(
            headLocated, headLocation.locationFlags, requiredHeadFlags)) {
        return;
    }

    glm::vec3 headPosition = xrVecToGlm(headLocation.pose.position);
    glm::quat headOrientation = xrQuatToGlm(headLocation.pose.orientation);
    _context->_lastHeadPose = controller::Pose(headPosition, headOrientation);

    _currentPresentFrameInfo.presentPose = _context->_lastHeadPose.getMatrix();
    _currentPresentFrameInfo.predictedDisplayTime = _lastFrameState.predictedDisplayTime / 1e9;
}

int OpenXrDisplayPlugin::getRequiredThreadCount() const {
    return HmdDisplayPlugin::getRequiredThreadCount();
}

QRectF OpenXrDisplayPlugin::getPlayAreaRect() {
    return QRectF(0, 0, 10, 10);
}

DisplayPlugin::StencilMaskMeshOperator OpenXrDisplayPlugin::getStencilMaskMeshOperator() {
    return nullptr;
}
