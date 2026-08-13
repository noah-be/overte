//
//  GL41BackendTexture.cpp
//  libraries/gpu/src/gpu
//
//  Created by Sam Gateau on 1/19/2015.
//  Copyright 2014 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//
#include "GL41Backend.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <vector>

#include <QtCore/QDebug>
#include <QtGui/QImage>

#include <gpu/gl/GLFramebuffer.h>
#include <gpu/gl/GLTexture.h>

namespace gpu { namespace gl41 { 

class GL41Framebuffer : public gl::GLFramebuffer {
    using Parent = gl::GLFramebuffer;
    static GLuint allocate() {
        GLuint result;
        glGenFramebuffers(1, &result);
        return result;
    }
public:
    void update() override {
        GLint currentFBO = -1;
        glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &currentFBO);
        glBindFramebuffer(GL_FRAMEBUFFER, _fbo);
        gl::GLTexture* gltexture = nullptr;
        TexturePointer surface;
        if (_gpuObject.getColorStamps() != _colorStamps) {
            if (_gpuObject.hasColor()) {
                _colorBuffers.clear();
                static const GLenum colorAttachments[] = {
                    GL_COLOR_ATTACHMENT0,
                    GL_COLOR_ATTACHMENT1,
                    GL_COLOR_ATTACHMENT2,
                    GL_COLOR_ATTACHMENT3,
                    GL_COLOR_ATTACHMENT4,
                    GL_COLOR_ATTACHMENT5,
                    GL_COLOR_ATTACHMENT6,
                    GL_COLOR_ATTACHMENT7,
                    GL_COLOR_ATTACHMENT8,
                    GL_COLOR_ATTACHMENT9,
                    GL_COLOR_ATTACHMENT10,
                    GL_COLOR_ATTACHMENT11,
                    GL_COLOR_ATTACHMENT12,
                    GL_COLOR_ATTACHMENT13,
                    GL_COLOR_ATTACHMENT14,
                    GL_COLOR_ATTACHMENT15 };

                int unit = 0;
                auto backend = _backend.lock();
                for (auto& b : _gpuObject.getRenderBuffers()) {
                    surface = b._texture;
                    if (surface) {
                        Q_ASSERT(TextureUsageType::RENDERBUFFER == surface->getUsageType());
                        gltexture = backend->syncGPUObject(surface); 
                    } else {
                        gltexture = nullptr;
                    }

                    if (gltexture) {
                        if (gltexture->_target == GL_TEXTURE_2D) {
                            glFramebufferTexture2D(GL_FRAMEBUFFER, colorAttachments[unit], GL_TEXTURE_2D, gltexture->_texture, 0);
                        } else if (gltexture->_target == GL_TEXTURE_2D_MULTISAMPLE) {
                            glFramebufferTexture2D(GL_FRAMEBUFFER, colorAttachments[unit], GL_TEXTURE_2D_MULTISAMPLE, gltexture->_texture, 0);
                        } else {
                            glFramebufferTextureLayer(GL_FRAMEBUFFER, colorAttachments[unit], gltexture->_texture, 0,
                                                      b._subresource);
                        }
                        _colorBuffers.push_back(colorAttachments[unit]);
                    } else {
                        glFramebufferTexture2D(GL_FRAMEBUFFER, colorAttachments[unit], GL_TEXTURE_2D, 0, 0);
                    }
                    unit++;
                }
            }
            _colorStamps = _gpuObject.getColorStamps();
        }

        GLenum attachement = GL_DEPTH_STENCIL_ATTACHMENT;
        if (!_gpuObject.hasStencil()) {
            attachement = GL_DEPTH_ATTACHMENT;
        } else if (!_gpuObject.hasDepth()) {
            attachement = GL_STENCIL_ATTACHMENT;
        }

        if (_gpuObject.getDepthStamp() != _depthStamp) {
            auto backend = _backend.lock();
            auto surface = _gpuObject.getDepthStencilBuffer();
            if (_gpuObject.hasDepthStencil() && surface) {
                Q_ASSERT(TextureUsageType::RENDERBUFFER == surface->getUsageType());
                gltexture = backend->syncGPUObject(surface);
            }

            if (gltexture) {
                if (gltexture->_target == GL_TEXTURE_2D) {
                    glFramebufferTexture2D(GL_FRAMEBUFFER, attachement, GL_TEXTURE_2D, gltexture->_texture, 0);
                } else if (gltexture->_target == GL_TEXTURE_2D_MULTISAMPLE) {
                    glFramebufferTexture2D(GL_FRAMEBUFFER, attachement, GL_TEXTURE_2D_MULTISAMPLE, gltexture->_texture, 0);
                } else {
                    glFramebufferTextureLayer(GL_FRAMEBUFFER, attachement, gltexture->_texture, 0,
                                              _gpuObject.getDepthStencilBufferSubresource());
                }
            } else {
                glFramebufferTexture2D(GL_FRAMEBUFFER, attachement, GL_TEXTURE_2D, 0, 0);
            }
            _depthStamp = _gpuObject.getDepthStamp();
        }


        // Last but not least, define where we draw
        if (!_colorBuffers.empty()) {
            glDrawBuffers((GLsizei)_colorBuffers.size(), _colorBuffers.data());
        } else {
            glDrawBuffer(GL_NONE);
        }

        // Now check for completness
        _status = glCheckFramebufferStatus(GL_FRAMEBUFFER);

        // restore the current framebuffer
        if (currentFBO != -1) {
            glBindFramebuffer(GL_DRAW_FRAMEBUFFER, currentFBO);
        }

        checkStatus();
    }


public:
    GL41Framebuffer(const std::weak_ptr<gl::GLBackend>& backend, const gpu::Framebuffer& framebuffer)
        : Parent(backend, framebuffer, allocate()) { }
};

gl::GLFramebuffer* GL41Backend::syncGPUObject(const Framebuffer& framebuffer) {
    return GL41Framebuffer::sync<GL41Framebuffer>(*this, framebuffer);
}

GLuint GL41Backend::getFramebufferID(const FramebufferPointer& framebuffer) {
    return framebuffer ? GL41Framebuffer::getId<GL41Framebuffer>(*this, *framebuffer) : 0;
}

void GL41Backend::do_blit(const Batch& batch, size_t paramOffset) {
    auto srcframebuffer = batch._framebuffers.get(batch._params[paramOffset]._uint);
    Vec4i srcvp;
    for (auto i = 0; i < 4; ++i) {
        srcvp[i] = batch._params[paramOffset + 1 + i]._int;
    }

    auto dstframebuffer = batch._framebuffers.get(batch._params[paramOffset + 5]._uint);
    Vec4i dstvp;
    for (auto i = 0; i < 4; ++i) {
        dstvp[i] = batch._params[paramOffset + 6 + i]._int;
    }

    // Assign dest framebuffer if not bound already
    auto newDrawFBO = getFramebufferID(dstframebuffer);
    if (_output._drawFBO != newDrawFBO) {
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, newDrawFBO);
    }

    // always bind the read fbo
    glBindFramebuffer(GL_READ_FRAMEBUFFER, getFramebufferID(srcframebuffer));

#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)
    // glBlitFramebuffer is affected by the scissor test, but Batch::blit has
    // its own explicit source and destination rectangles and no scissor
    // argument.  A draw job may leave scissoring enabled before the neutral
    // tone-map transfer, causing Apple's GL implementation to copy no pixels.
    // Keep the backend state cache coherent by restoring the driver state
    // immediately after the transfer.
    const bool neutralToneMapBlit = batch.getName() == "ToneMapNeutralBlit::run";
    const bool scissorWasEnabled = neutralToneMapBlit && glIsEnabled(GL_SCISSOR_TEST);
    GLint readBufferBefore { 0 };
    GLint drawBufferBefore { 0 };
    GLint scissorBox[4] { 0, 0, 0, 0 };
    if (neutralToneMapBlit) {
        glGetIntegerv(GL_READ_BUFFER, &readBufferBefore);
        glGetIntegerv(GL_DRAW_BUFFER0, &drawBufferBefore);
        glGetIntegerv(GL_SCISSOR_BOX, scissorBox);
        if (scissorWasEnabled) {
            glDisable(GL_SCISSOR_TEST);
        }
        // Framebuffer read-buffer selection is stored per FBO.  Select the
        // attachment Batch::blit is defined to copy instead of inheriting an
        // unrelated job's selection.
        glReadBuffer(GL_COLOR_ATTACHMENT0);
        while (glGetError() != GL_NO_ERROR) {
            // Attribute the error sampled below to glBlitFramebuffer rather
            // than to an earlier diagnostic query.
        }
    }
#endif

    // Blit!
    glBlitFramebuffer(srcvp.x, srcvp.y, srcvp.z, srcvp.w, 
        dstvp.x, dstvp.y, dstvp.z, dstvp.w,
        GL_COLOR_BUFFER_BIT, GL_LINEAR);

#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)
    GLenum neutralToneMapBlitError { GL_NO_ERROR };
    if (neutralToneMapBlit) {
        neutralToneMapBlitError = glGetError();
        if (neutralToneMapBlitError != GL_NO_ERROR) {
            qWarning().noquote() << "OVERTE_MACOS_GL_BLIT_ERROR"
                                 << "error=" << neutralToneMapBlitError;
        }
        if (scissorWasEnabled) {
            glEnable(GL_SCISSOR_TEST);
        }

        // When diagnostics are requested, wait until representative source
        // pixels exist and then record one bounded before/after probe.  This
        // distinguishes a failed transfer from a later composite overwrite
        // without dumping textures, paths, arguments or environment data.
        static bool transferProbeLogged { false };
        if (!transferProbeLogged && qEnvironmentVariableIsSet("OVERTE_MACOS_GL_DIAGNOSTICS")) {
            const auto srcWidth = std::abs(srcvp.z - srcvp.x);
            const auto srcHeight = std::abs(srcvp.w - srcvp.y);
            const auto dstWidth = std::abs(dstvp.z - dstvp.x);
            const auto dstHeight = std::abs(dstvp.w - dstvp.y);
            if (srcWidth > 0 && srcHeight > 0 && dstWidth > 0 && dstHeight > 0) {
                const std::array<int, 3> sourceRows {
                    std::min(srcvp.y, srcvp.w) + srcHeight / 8,
                    std::min(srcvp.y, srcvp.w) + srcHeight / 4,
                    std::min(srcvp.y, srcvp.w) + srcHeight / 2
                };
                const std::array<int, 3> destinationRows {
                    std::min(dstvp.y, dstvp.w) + dstHeight / 8,
                    std::min(dstvp.y, dstvp.w) + dstHeight / 4,
                    std::min(dstvp.y, dstvp.w) + dstHeight / 2
                };
                std::vector<uint8_t> sourcePixels(static_cast<size_t>(srcWidth) * 4);
                std::vector<uint8_t> destinationPixels(static_cast<size_t>(dstWidth) * 4);
                bool sourceNonzero { false };
                bool destinationNonzero { false };
                const auto hasNonzeroRGB = [](const std::vector<uint8_t>& pixels) {
                    for (size_t index = 0; index + 3 < pixels.size(); index += 4) {
                        if (pixels[index] != 0 || pixels[index + 1] != 0 || pixels[index + 2] != 0) {
                            return true;
                        }
                    }
                    return false;
                };

                glBindFramebuffer(GL_READ_FRAMEBUFFER, getFramebufferID(srcframebuffer));
                glReadBuffer(GL_COLOR_ATTACHMENT0);
                for (const auto row : sourceRows) {
                    glReadPixels(std::min(srcvp.x, srcvp.z), row, srcWidth, 1,
                        GL_RGBA, GL_UNSIGNED_BYTE, sourcePixels.data());
                    sourceNonzero = sourceNonzero || hasNonzeroRGB(sourcePixels);
                }

                if (sourceNonzero) {
                    glBindFramebuffer(GL_READ_FRAMEBUFFER, getFramebufferID(dstframebuffer));
                    glReadBuffer(GL_COLOR_ATTACHMENT0);
                    for (const auto row : destinationRows) {
                        glReadPixels(std::min(dstvp.x, dstvp.z), row, dstWidth, 1,
                            GL_RGBA, GL_UNSIGNED_BYTE, destinationPixels.data());
                        destinationNonzero = destinationNonzero || hasNonzeroRGB(destinationPixels);
                    }
                    transferProbeLogged = true;
                    qInfo().noquote() << "OVERTE_MACOS_GL_BLIT"
                                      << "source_nonzero=" << sourceNonzero
                                      << "destination_nonzero=" << destinationNonzero
                                      << "error=" << neutralToneMapBlitError
                                      << "read_buffer=" << readBufferBefore
                                      << "draw_buffer=" << drawBufferBefore
                                      << "scissor_enabled=" << scissorWasEnabled
                                      << "scissor=" << scissorBox[0] << scissorBox[1]
                                      << scissorBox[2] << scissorBox[3]
                                      << "source_size=" << srcWidth << srcHeight
                                      << "destination_size=" << dstWidth << dstHeight;
                }
            }
        }
    }
#endif

    // Always clean the read fbo to 0
    glBindFramebuffer(GL_READ_FRAMEBUFFER, 0);

    // Restore draw fbo if changed
    if (_output._drawFBO != newDrawFBO) {
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, _output._drawFBO);
    }

#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)
    if (!neutralToneMapBlit || neutralToneMapBlitError == GL_NO_ERROR) {
        (void) CHECK_GL_ERROR();
    }
#else
    (void) CHECK_GL_ERROR();
#endif
}


} }
