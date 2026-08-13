//
//  GLBackendTexture.cpp
//  libraries/gpu/src/gpu
//
//  Created by Sam Gateau on 1/19/2015.
//  Copyright 2014 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//
#include "GLBackend.h"
#include "GLShared.h"
#include "GLFramebuffer.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

#include <QtCore/QDebug>
#include <QtGui/QImage>

using namespace gpu;
using namespace gpu::gl;

void GLBackend::syncOutputStateCache() {
    GLint currentFBO;
    glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &currentFBO);

    _output._drawFBO = currentFBO;
    reset(_output._framebuffer);
}

void GLBackend::resetOutputStage() {
    if (valid(_output._framebuffer)) {
        reset(_output._framebuffer);
        _output._drawFBO = 0;
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0);
    }

    glEnable(GL_FRAMEBUFFER_SRGB);
}

void GLBackend::do_setFramebuffer(const Batch& batch, size_t paramOffset) {
    const auto& framebuffer = batch._framebuffers.get(batch._params[paramOffset]._uint);
    setFramebuffer(framebuffer);
}

void GLBackend::do_setFramebufferSwapChain(const Batch& batch, size_t paramOffset) {
    auto swapChain = std::static_pointer_cast<FramebufferSwapChain>(batch._swapChains.get(batch._params[paramOffset]._uint));
    if (swapChain) {
        auto index = batch._params[paramOffset + 1]._uint;
        const auto& framebuffer = swapChain->get(index);
        setFramebuffer(framebuffer);
    }
}

void GLBackend::setFramebuffer(const FramebufferPointer& framebuffer) {
    if (!compare(_output._framebuffer, framebuffer)) {
        auto newFBO = getFramebufferID(framebuffer);
        if (_output._drawFBO != newFBO) {
            _output._drawFBO = newFBO;
            glBindFramebuffer(GL_DRAW_FRAMEBUFFER, newFBO);
        }
        assign(_output._framebuffer, framebuffer);
    }

#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)
    // Apple Software OpenGL incorrectly applies FRAMEBUFFER_SRGB to linear
    // offscreen attachments instead of treating it as a no-op. Select the
    // conversion state from the actual bound color attachment, and restore it
    // automatically when a later sRGB/default framebuffer is selected.
    bool enableFramebufferSRGB = !framebuffer;
    GLint colorEncoding { GL_LINEAR };
    if (framebuffer && framebuffer->hasColor()) {
        glGetFramebufferAttachmentParameteriv(GL_DRAW_FRAMEBUFFER,
            GL_COLOR_ATTACHMENT0, GL_FRAMEBUFFER_ATTACHMENT_COLOR_ENCODING,
            &colorEncoding);
        enableFramebufferSRGB = colorEncoding == GL_SRGB;
    }
    if (enableFramebufferSRGB) {
        glEnable(GL_FRAMEBUFFER_SRGB);
    } else {
        glDisable(GL_FRAMEBUFFER_SRGB);
    }

    static thread_local bool loggedLinearFramebuffer { false };
    if (!enableFramebufferSRGB && !loggedLinearFramebuffer &&
            qEnvironmentVariableIsSet("OVERTE_MACOS_GL_DIAGNOSTICS")) {
        loggedLinearFramebuffer = true;
        qInfo().noquote() << "OVERTE_MACOS_FRAMEBUFFER_SRGB"
                          << "fbo=" << _output._drawFBO
                          << "encoding=" << colorEncoding
                          << "enabled=0";
    }
#endif
}

void GLBackend::do_advance(const Batch& batch, size_t paramOffset) {
    auto ringbuffer = batch._swapChains.get(batch._params[paramOffset]._uint);
    if (ringbuffer) {
        ringbuffer->advance();
    }
}

void GLBackend::do_clearFramebuffer(const Batch& batch, size_t paramOffset) {
    if (_stereo.isStereo() && !_pipeline._stateCache.flags.scissorEnable) {
        qWarning("Clear without scissor in stereo mode");
    }

    uint32 masks = batch._params[paramOffset + 7]._uint;
    Vec4 color;
    color.x = batch._params[paramOffset + 6]._float;
    color.y = batch._params[paramOffset + 5]._float;
    color.z = batch._params[paramOffset + 4]._float;
    color.w = batch._params[paramOffset + 3]._float;
    float depth = batch._params[paramOffset + 2]._float;
    int stencil = batch._params[paramOffset + 1]._int;
    int useScissor = batch._params[paramOffset + 0]._int;

    GLuint glmask = 0;
    bool restoreStencilMask = false;
    uint8_t cacheStencilMask = 0xFF;
    if (masks & Framebuffer::BUFFER_STENCIL) {
        glClearStencil(stencil);
        glmask |= GL_STENCIL_BUFFER_BIT;

        cacheStencilMask = _pipeline._stateCache.stencilActivation.getWriteMaskFront();
        if (cacheStencilMask != 0xFF) {
            restoreStencilMask = true;
            glStencilMask( 0xFF);
        }
    }

    bool restoreDepthMask = false;
    if (masks & Framebuffer::BUFFER_DEPTH) {
        glClearDepthf(depth);
        glmask |= GL_DEPTH_BUFFER_BIT;
        
        bool cacheDepthMask = _pipeline._stateCache.depthTest.getWriteMask();
        if (!cacheDepthMask) {
            restoreDepthMask = true;
            glDepthMask(GL_TRUE);
        }
    }

    std::vector<GLenum> drawBuffers;
    auto framebuffer = acquire(_output._framebuffer);
    if (masks & Framebuffer::BUFFER_COLORS) {
        if (framebuffer) {
            for (unsigned int i = 0; i < Framebuffer::MAX_NUM_RENDER_BUFFERS; i++) {
                if (masks & (1 << i)) {
                    drawBuffers.push_back(GL_COLOR_ATTACHMENT0 + i);
                }
            }

            if (!drawBuffers.empty()) {
                glDrawBuffers((GLsizei)drawBuffers.size(), drawBuffers.data());
                glClearColor(color.x, color.y, color.z, color.w);
                glmask |= GL_COLOR_BUFFER_BIT;
            
                (void) CHECK_GL_ERROR();
            }
        } else {
            glClearColor(color.x, color.y, color.z, color.w);
            glmask |= GL_COLOR_BUFFER_BIT;
        }
        
        // Force the color mask cache to WRITE_ALL if not the case
        do_setStateColorWriteMask(State::ColorMask::WRITE_ALL);
    }

    // Apply scissor if needed and if not already on
    bool doEnableScissor = (useScissor && (!_pipeline._stateCache.flags.scissorEnable));
    if (doEnableScissor) {
        glEnable(GL_SCISSOR_TEST);
    }

    // Clear!
    glClear(glmask);

    // Restore scissor if needed
    if (doEnableScissor) {
        glDisable(GL_SCISSOR_TEST);
    }

    // Restore Stencil write mask
    if (restoreStencilMask) {
        glStencilMask(cacheStencilMask);
    }

    // Restore write mask meaning turn back off
    if (restoreDepthMask) {
        glDepthMask(GL_FALSE);
    }
    
    // Restore the color draw buffers only if a frmaebuffer is bound
    if (framebuffer && !drawBuffers.empty()) {
        auto glFramebuffer = syncGPUObject(*framebuffer);
        if (glFramebuffer) {
            glDrawBuffers((GLsizei)glFramebuffer->_colorBuffers.size(), glFramebuffer->_colorBuffers.data());
        }
    }

    (void) CHECK_GL_ERROR();
}

void GLBackend::downloadFramebuffer(const FramebufferPointer& srcFramebuffer, const Vec4i& region, QImage& destImage) {
    auto readFBO = getFramebufferID(srcFramebuffer);
    if (srcFramebuffer && readFBO) {
        if ((srcFramebuffer->getWidth() < (region.x + region.z)) || (srcFramebuffer->getHeight() < (region.y + region.w))) {
          qCWarning(gpugllogging) << "GLBackend::downloadFramebuffer : srcFramebuffer is too small to provide the region queried";
          return;
        }
    }

    if ((destImage.width() < region.z) || (destImage.height() < region.w)) {
          qCWarning(gpugllogging) << "GLBackend::downloadFramebuffer : destImage is too small to receive the region of the framebuffer";
          return;
    }

    GLenum format = GL_BGRA;
    auto backendApi = hifi::properties::getGraphicsAPI();
    if (backendApi == hifi::properties::GraphicsAPI::GLES32) {
        format = GL_RGBA;
    }
    if (destImage.format() != QImage::Format_ARGB32) {
          qCWarning(gpugllogging) << "GLBackend::downloadFramebuffer : destImage format must be FORMAT_ARGB32 to receive the region of the framebuffer";
          return;
    }

    glBindFramebuffer(GL_READ_FRAMEBUFFER, getFramebufferID(srcFramebuffer));
    glReadPixels(region.x, region.y, region.z, region.w, format, GL_UNSIGNED_BYTE, destImage.bits());
    glBindFramebuffer(GL_READ_FRAMEBUFFER, 0);

    (void) CHECK_GL_ERROR();
}

#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)
void GLBackend::diagnoseFramebuffer(const FramebufferPointer& framebuffer, const Vec4i& region, const char* label) {
    const auto framebufferID = getFramebufferID(framebuffer);
    if (!framebuffer || !framebufferID || region.z <= 0 || region.w <= 0) {
        qInfo().noquote() << "OVERTE_MACOS_GL_FRAMEBUFFER"
                          << "label=" << label << "available=false";
        return;
    }

    const auto pixelCount = static_cast<size_t>(region.z) * static_cast<size_t>(region.w);
    std::vector<float> floatPixels(pixelCount * 4);
    std::vector<uint8_t> bytePixels(pixelCount * 4);
    GLint colorEncoding { 0 };
    GLint componentType { 0 };

    glBindFramebuffer(GL_READ_FRAMEBUFFER, framebufferID);
    glGetFramebufferAttachmentParameteriv(GL_READ_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
        GL_FRAMEBUFFER_ATTACHMENT_COLOR_ENCODING, &colorEncoding);
    glGetFramebufferAttachmentParameteriv(GL_READ_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
        GL_FRAMEBUFFER_ATTACHMENT_COMPONENT_TYPE, &componentType);
    glReadPixels(region.x, region.y, region.z, region.w, GL_RGBA, GL_FLOAT, floatPixels.data());
    glReadPixels(region.x, region.y, region.z, region.w, GL_RGBA, GL_UNSIGNED_BYTE, bytePixels.data());
    glBindFramebuffer(GL_READ_FRAMEBUFFER, 0);

    float floatMin { std::numeric_limits<float>::max() };
    float floatMax { std::numeric_limits<float>::lowest() };
    uint8_t byteMin { std::numeric_limits<uint8_t>::max() };
    uint8_t byteMax { std::numeric_limits<uint8_t>::lowest() };
    size_t finiteRGB { 0 };
    size_t nonzeroFloatRGB { 0 };
    size_t nonzeroByteRGB { 0 };
    for (size_t pixel = 0; pixel < pixelCount; ++pixel) {
        for (size_t channel = 0; channel < 3; ++channel) {
            const auto index = pixel * 4 + channel;
            const auto floatValue = floatPixels[index];
            if (std::isfinite(floatValue)) {
                floatMin = std::min(floatMin, floatValue);
                floatMax = std::max(floatMax, floatValue);
                ++finiteRGB;
                nonzeroFloatRGB += floatValue > 0.0f;
            }
            byteMin = std::min(byteMin, bytePixels[index]);
            byteMax = std::max(byteMax, bytePixels[index]);
            nonzeroByteRGB += bytePixels[index] > 0;
        }
    }

    qInfo().noquote() << "OVERTE_MACOS_GL_FRAMEBUFFER"
                      << "label=" << label
                      << "name=" << QString::fromStdString(framebuffer->getName())
                      << "encoding=" << colorEncoding
                      << "component_type=" << componentType
                      << "samples=" << framebuffer->getNumSamples()
                      << "float_min=" << (finiteRGB ? floatMin : 0.0f)
                      << "float_max=" << (finiteRGB ? floatMax : 0.0f)
                      << "float_nonzero=" << nonzeroFloatRGB
                      << "byte_min=" << static_cast<int>(byteMin)
                      << "byte_max=" << static_cast<int>(byteMax)
                      << "byte_nonzero=" << nonzeroByteRGB;
    (void) CHECK_GL_ERROR();
}
#endif
