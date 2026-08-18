//
//  FramebufferCache.cpp
//  interface/src/renderer
//
//  Created by Andrzej Kapolka on 8/6/13.
//  Copyright 2013 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "FramebufferCache.h"

#include <glm/glm.hpp>
#include <gpu/Format.h>
#include <gpu/Framebuffer.h>

#include "RenderUtilsLogging.h"

void FramebufferCache::setFrameBufferSize(QSize frameBufferSize) {
    //If the size changed, we need to delete our FBOs
    if (_frameBufferSize != frameBufferSize) {
        _frameBufferSize = frameBufferSize;
        {
            std::unique_lock<std::mutex> lock(_mutex);
            _cachedFramebuffers.clear();
        }
    }
}

void FramebufferCache::createPrimaryFramebuffer() {
    auto defaultSampler = Sampler(Sampler::FILTER_MIN_MAG_POINT);

    auto smoothSampler = Sampler(Sampler::FILTER_MIN_MAG_MIP_LINEAR);
}


gpu::FramebufferPointer FramebufferCache::getFramebuffer() {
    std::unique_lock<std::mutex> lock(_mutex);
    if (_cachedFramebuffers.empty()) {
#if defined(Q_OS_IOS)
        // Match MoltenVK's native iOS swapchain format so presentation can use
        // a direct image copy instead of a Metal format-conversion blit.
        const auto colorFormat = gpu::Element::COLOR_SBGRA_32;
#else
        const auto colorFormat = gpu::Element::COLOR_SRGBA_32;
#endif
        _cachedFramebuffers.push_back(gpu::FramebufferPointer(gpu::Framebuffer::create("cached", colorFormat, gpu::Element::DEPTH24_STENCIL8, _frameBufferSize.width(), _frameBufferSize.height())));
    }
    gpu::FramebufferPointer result = _cachedFramebuffers.front();
    _cachedFramebuffers.pop_front();
    return result;
}

void FramebufferCache::releaseFramebuffer(const gpu::FramebufferPointer& framebuffer) {
    std::unique_lock<std::mutex> lock(_mutex);
    if (QSize(framebuffer->getSize().x, framebuffer->getSize().y) == _frameBufferSize) {
        _cachedFramebuffers.push_back(framebuffer);
    }
}
