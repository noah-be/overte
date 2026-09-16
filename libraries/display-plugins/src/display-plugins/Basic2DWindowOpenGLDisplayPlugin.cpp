//
//  Created by Bradley Austin Davis on 2015/05/29
//  Copyright 2015 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//
#include "Basic2DWindowOpenGLDisplayPlugin.h"
#include "CompositorHelper.h"
#include "VirtualPadManager.h"

#include <mutex>

#include <QScreen>
#include <QtGui/QWindow>
#include <QtGui/QGuiApplication>
#include <QtWidgets/QAction>

#include <ui-plugins/PluginContainer.h>
#include <PathUtils.h>
#include "SettingHandle.h"
#include "ScreenName.h"
#include <PhoneLoadingDiagnostics.h>


const QString Basic2DWindowOpenGLDisplayPlugin::NAME("Desktop");

static const QString FULLSCREEN = "Fullscreen";

#if defined(Q_OS_ANDROID)
#if defined(ANDROID_APP_PHONE_INTERFACE)
constexpr uint16_t VIRTUAL_PAD_MIP_COUNT { gpu::Texture::SINGLE_MIP };
constexpr Sampler::Filter VIRTUAL_PAD_FILTER { Sampler::FILTER_MIN_MAG_LINEAR };
#else
constexpr uint16_t VIRTUAL_PAD_MIP_COUNT { gpu::Texture::MAX_NUM_MIPS };
constexpr Sampler::Filter VIRTUAL_PAD_FILTER { Sampler::FILTER_MIN_MAG_MIP_LINEAR };
#endif
#endif

void Basic2DWindowOpenGLDisplayPlugin::customizeContext() {
#if defined(Q_OS_ANDROID)
    QScreen* virtualPadScreen = getFullscreenTarget();
    qreal dpi = virtualPadScreen->physicalDotsPerInch();
    _virtualPadPixelSize = dpi * VirtualPad::Manager::BASE_DIAMETER_PIXELS / VirtualPad::Manager::DPI;

    if (!_virtualPadStickTexture) {
        auto iconPath = PathUtils::resourcesPath() + "images/analog_stick.png";
        auto image = QImage(iconPath);
        if (image.format() != QImage::Format_ARGB32) {
            image = image.convertToFormat(QImage::Format_ARGB32);
        }
        if ((image.width() > 0) && (image.height() > 0)) {
#if !defined(ANDROID_APP_PHONE_INTERFACE)
            image = image.scaled(_virtualPadPixelSize, _virtualPadPixelSize, Qt::KeepAspectRatio);
#endif

            _virtualPadStickTexture = gpu::Texture::createStrict(
                    gpu::Element(gpu::VEC4, gpu::NUINT8, gpu::RGBA),
                    image.width(), image.height(),
                    VIRTUAL_PAD_MIP_COUNT,
                    Sampler(VIRTUAL_PAD_FILTER));
            _virtualPadStickTexture->setSource("virtualPad stick");
            auto usage = gpu::Texture::Usage::Builder().withColor().withAlpha();
            _virtualPadStickTexture->setUsage(usage.build());
            _virtualPadStickTexture->setStoredMipFormat(gpu::Element(gpu::VEC4, gpu::NUINT8, gpu::RGBA));
            _virtualPadStickTexture->assignStoredMip(0, image.byteCount(), image.constBits());
#if !defined(ANDROID_APP_PHONE_INTERFACE)
            _virtualPadStickTexture->setAutoGenerateMips(true);
#endif
        }
    }

    if (!_virtualPadStickBaseTexture) {
        auto iconPath = PathUtils::resourcesPath() + "images/analog_stick_base.png";
        auto image = QImage(iconPath);
        if (image.format() != QImage::Format_ARGB32) {
            image = image.convertToFormat(QImage::Format_ARGB32);
        }
        if ((image.width() > 0) && (image.height() > 0)) {
#if !defined(ANDROID_APP_PHONE_INTERFACE)
            image = image.scaled(_virtualPadPixelSize, _virtualPadPixelSize, Qt::KeepAspectRatio);
#endif

            _virtualPadStickBaseTexture = gpu::Texture::createStrict(
                    gpu::Element(gpu::VEC4, gpu::NUINT8, gpu::RGBA),
                    image.width(), image.height(),
                    VIRTUAL_PAD_MIP_COUNT,
                    Sampler(VIRTUAL_PAD_FILTER));
            _virtualPadStickBaseTexture->setSource("virtualPad base");
            auto usage = gpu::Texture::Usage::Builder().withColor().withAlpha();
            _virtualPadStickBaseTexture->setUsage(usage.build());
            _virtualPadStickBaseTexture->setStoredMipFormat(gpu::Element(gpu::VEC4, gpu::NUINT8, gpu::RGBA));
            _virtualPadStickBaseTexture->assignStoredMip(0, image.byteCount(), image.constBits());
#if !defined(ANDROID_APP_PHONE_INTERFACE)
            _virtualPadStickBaseTexture->setAutoGenerateMips(true);
#endif
        }
    }

    if (_virtualPadButtons.size() == 0) {
        _virtualPadButtons.append(VirtualPadButton(
                dpi * VirtualPad::Manager::BTN_FULL_PIXELS / VirtualPad::Manager::DPI,
                PathUtils::resourcesPath() + "images/fly.png",
                VirtualPad::Manager::Button::JUMP));
        _virtualPadButtons.append(VirtualPadButton(
                dpi * VirtualPad::Manager::BTN_FULL_PIXELS / VirtualPad::Manager::DPI,
                PathUtils::resourcesPath() + "images/handshake.png",
                VirtualPad::Manager::Button::HANDSHAKE));
    }
#if defined(ANDROID_APP_PHONE_INTERFACE)
    if (phoneLoadingDiagnosticsEnabled()) {
        // Context setup can precede Android's final screen metrics. Record the
        // actual cached button sizes as well as the freshly calculated size.
        static thread_local QString previousMetrics;
        static thread_local unsigned metricCount { 0 };
        if (metricCount < 32) {
            const auto pixels = virtualPadScreen->size();
            const auto available = virtualPadScreen->availableSize();
            const auto millimeters = virtualPadScreen->physicalSize();
            const QString metrics = QString::asprintf(
                "phase=controls_display_metrics dpi=%.5f screen_w=%d screen_h=%d available_w=%d available_h=%d physical_w_mm=%.5f physical_h_mm=%.5f dpr=%.5f pad_px=%.5f desired_button_px=%.5f jump_px=%.5f handshake_px=%.5f pad_texture_w=%d pad_texture_h=%d",
                double(dpi), pixels.width(), pixels.height(), available.width(), available.height(),
                double(millimeters.width()), double(millimeters.height()), double(virtualPadScreen->devicePixelRatio()),
                double(_virtualPadPixelSize), double(dpi * VirtualPad::Manager::BTN_FULL_PIXELS / VirtualPad::Manager::DPI),
                double(_virtualPadButtons.at(0)._pixelSize), double(_virtualPadButtons.at(1)._pixelSize),
                _virtualPadStickBaseTexture ? int(_virtualPadStickBaseTexture->getWidth()) : 0,
                _virtualPadStickBaseTexture ? int(_virtualPadStickBaseTexture->getHeight()) : 0);
            if (metricCount == 0 || metrics != previousMetrics) {
                ++metricCount;
                PHONE_LOADING("%s sample=%u cap_reached=%d", qPrintable(metrics), metricCount, metricCount == 32);
                previousMetrics = metrics;
            }
        }
    }
#endif
#endif
    Parent::customizeContext();
}

void Basic2DWindowOpenGLDisplayPlugin::uncustomizeContext() {
    Parent::uncustomizeContext();
}

bool Basic2DWindowOpenGLDisplayPlugin::internalActivate() {
    _framerateActions.clear();
#if defined(Q_OS_ANDROID)
    _container->setFullscreen(nullptr, true);
#endif
    _container->addMenuItem(PluginType::DISPLAY_PLUGIN, MENU_PATH(), FULLSCREEN,
        [this](bool clicked) {
            if (clicked) {
                _container->setFullscreen(getFullscreenTarget());
            } else {
                _container->unsetFullscreen();
            }
        }, true, false);

    return Parent::internalActivate();
}

void Basic2DWindowOpenGLDisplayPlugin::compositeExtra() {
#if defined(Q_OS_ANDROID)
    auto& virtualPadManager = VirtualPad::Manager::instance();
#if defined(ANDROID_APP_PHONE_INTERFACE)
    // Input publishes a complete layout after updating its hit targets. Never
    // sample QScreen on the presentation thread or retain startup fallback DPI.
    const auto phoneLayout = virtualPadManager.getPhoneLayout();
    const bool phoneLayoutReady = phoneLayout.revision != 0;
    if (phoneLayoutReady) {
        _virtualPadPixelSize = phoneLayout.padDiameter;
        for (auto& button : _virtualPadButtons) {
            button._pixelSize = phoneLayout.buttonDiameter;
        }
        if (phoneLoadingDiagnosticsEnabled()) {
            static thread_local uint64_t previousRevision { 0 };
            static thread_local unsigned sampleCount { 0 };
            if (sampleCount < 32 && previousRevision != phoneLayout.revision) {
                ++sampleCount;
                PHONE_LOADING("phase=controls_applied_metrics revision=%llu pad_px=%.5f button_px=%.5f button_radius_px=%.5f buttons_visible=%d sample=%u cap_reached=%d",
                    (unsigned long long)phoneLayout.revision, double(phoneLayout.padDiameter),
                    double(phoneLayout.buttonDiameter), double(phoneLayout.buttonRadius),
                    phoneLayout.buttonsVisible, sampleCount, sampleCount == 32);
                previousRevision = phoneLayout.revision;
            }
        }
    }
    if (phoneLayoutReady && virtualPadManager.getLeftVirtualPad()->isShown()) {
        const glm::vec2 center(phoneLayout.centerX, phoneLayout.centerY);
        const auto stickPosition = virtualPadManager.getLeftVirtualPad()->getCurrentTouch();
        auto stickBaseTransform = DependencyManager::get<CompositorHelper>()->getPoint2DTransform(
            center, _virtualPadPixelSize, _virtualPadPixelSize);
        auto stickTransform = DependencyManager::get<CompositorHelper>()->getPoint2DTransform(
            stickPosition, _virtualPadPixelSize, _virtualPadPixelSize);
#else
    if(virtualPadManager.getLeftVirtualPad()->isShown()) {
        // render stick base
        auto stickBaseTransform = DependencyManager::get<CompositorHelper>()->getPoint2DTransform(virtualPadManager.getLeftVirtualPad()->getFirstTouch(),
                                                                                                    _virtualPadPixelSize, _virtualPadPixelSize);
        auto stickTransform = DependencyManager::get<CompositorHelper>()->getPoint2DTransform(virtualPadManager.getLeftVirtualPad()->getCurrentTouch(),
                                                                                              _virtualPadPixelSize, _virtualPadPixelSize);
#endif

        render([&](gpu::Batch& batch) {
            batch.enableStereo(false);
            batch.setFramebuffer(_compositeFramebuffer);
            batch.resetViewTransform();
            batch.setProjectionTransform(mat4());
            batch.setPipeline(_cursorPipeline);

            batch.setResourceTexture(0, _virtualPadStickBaseTexture);
            batch.setModelTransform(stickBaseTransform);
            batch.draw(gpu::TRIANGLE_STRIP, 4);

            batch.setResourceTexture(0, _virtualPadStickTexture);
            batch.setModelTransform(stickTransform);
            batch.draw(gpu::TRIANGLE_STRIP, 4);

            foreach(VirtualPadButton virtualPadButton, _virtualPadButtons) {
#if defined(ANDROID_APP_PHONE_INTERFACE)
                if (phoneLayout.buttonsVisible) {
                    virtualPadButton.draw(batch, glm::vec2(phoneLayout.buttonX,
                        virtualPadButton._button == VirtualPad::Manager::Button::JUMP ? phoneLayout.jumpY : phoneLayout.secondaryY));
                }
#else
                virtualPadButton.draw(batch, virtualPadManager.getButtonPosition(virtualPadButton._button));
#endif
            }
        });
    }
#endif
    Parent::compositeExtra();
}

static const uint32_t MIN_THROTTLE_CHECK_FRAMES = 60;

bool Basic2DWindowOpenGLDisplayPlugin::isThrottled() const {
    static auto lastCheck = presentCount();
    // Don't access the menu API every single frame
    // TODO: if the check was expensive enough to not be done every frame, check if this doesn't create stutters.
    if ((presentCount() - lastCheck) > MIN_THROTTLE_CHECK_FRAMES) {
        static const QString ThrottleFPSIfNotFocus = "Throttle FPS If Not Focus"; // FIXME - this value duplicated in Menu.h
        _isThrottled  = (!_container->isForeground() && _container->isOptionChecked(ThrottleFPSIfNotFocus));
        lastCheck = presentCount();
    }

    return _isThrottled;
}

QScreen* Basic2DWindowOpenGLDisplayPlugin::getFullscreenTarget() {
    Setting::Handle<QString> _fullScreenScreenSetting { "fullScreenScreen", "" };
    QString selectedModel = _fullScreenScreenSetting.get();

    for(QScreen *screen : qApp->screens()) {
        if (ScreenName::getNameForScreen(screen) == selectedModel) {
            return screen;
        }
    }

    qWarning() << "Failed to find selected screen" << selectedModel << "for full screen mode, using primary screen";
    return qApp->primaryScreen();
}

#if defined(Q_OS_ANDROID)

Basic2DWindowOpenGLDisplayPlugin::VirtualPadButton::VirtualPadButton(qreal pixelSize,
                                                                     QString iconPath,
                                                                     VirtualPad::Manager::Button button) :
    _pixelSize { pixelSize },
    _button { button }
{
    if (!_texture) {
        auto image = QImage(iconPath);
        if (image.format() != QImage::Format_ARGB32) {
            image = image.convertToFormat(QImage::Format_ARGB32);
        }
        if ((image.width() > 0) && (image.height() > 0)) {
#if !defined(ANDROID_APP_PHONE_INTERFACE)
            image = image.scaled(_pixelSize, _pixelSize, Qt::KeepAspectRatio);
#endif
            image = image.mirrored();

            _texture = gpu::Texture::createStrict(
                    gpu::Element(gpu::VEC4, gpu::NUINT8, gpu::RGBA),
                    image.width(), image.height(),
                    VIRTUAL_PAD_MIP_COUNT,
                    Sampler(VIRTUAL_PAD_FILTER));
            _texture->setSource(iconPath.toStdString());
            auto usage = gpu::Texture::Usage::Builder().withColor().withAlpha();
            _texture->setUsage(usage.build());
            _texture->setStoredMipFormat(gpu::Element(gpu::VEC4, gpu::NUINT8, gpu::RGBA));
            _texture->assignStoredMip(0, image.byteCount(), image.constBits());
#if !defined(ANDROID_APP_PHONE_INTERFACE)
            _texture->setAutoGenerateMips(true);
#endif
        }
    }
}

void Basic2DWindowOpenGLDisplayPlugin::VirtualPadButton::draw(gpu::Batch &batch,
                                                              glm::vec2 buttonPosition) {
    auto transform = DependencyManager::get<CompositorHelper>()->getPoint2DTransform(
            buttonPosition,
            _pixelSize, _pixelSize);
    batch.setResourceTexture(0, _texture);
    batch.setModelTransform(transform);
    batch.draw(gpu::TRIANGLE_STRIP, 4);
}

#endif
