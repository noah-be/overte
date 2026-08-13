//
//  ToneMapAndResampleTask.cpp
//  libraries/render-utils/src
//
//  Created by Anna Brewer on 7/3/19.
//  Copyright 2019 High Fidelity, Inc.
//  Copyright 2024 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "ToneMapAndResampleTask.h"

#include "ToneMapDiagnostics.h"

#include <mutex>

#include <QtCore/QDebug>

#include <gpu/Context.h>
#include <shaders/Shaders.h>

#include "render-utils/ShaderConstants.h"
#include "StencilMaskPass.h"
#include "FramebufferCache.h"

using namespace render;
using namespace shader::gpu::program;
using namespace shader::render_utils::program;

gpu::PipelinePointer ToneMapAndResample::_pipeline;
gpu::PipelinePointer ToneMapAndResample::_mirrorPipeline;
#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)
gpu::PipelinePointer ToneMapAndResample::_passthroughPipeline;
gpu::PipelinePointer ToneMapAndResample::_mirrorPassthroughPipeline;
namespace {
std::mutex diagnosticMutex;
gpu::FramebufferPointer diagnosticInputFramebuffer;
std::once_flag diagnosticParametersOnce;
std::once_flag neutralPassthroughOnce;
}

gpu::FramebufferPointer getToneMapDiagnosticInputFramebuffer() {
    const std::lock_guard<std::mutex> guard(diagnosticMutex);
    return diagnosticInputFramebuffer;
}
#endif

ToneMapAndResample::ToneMapAndResample() {
    Parameters parameters;
    _parametersBuffer = gpu::BufferView(std::make_shared<gpu::Buffer>(gpu::Buffer::UniformBuffer, sizeof(Parameters), (const gpu::Byte*) &parameters));
}

void ToneMapAndResample::init() {
    // shared_ptr to gpu::State
    gpu::StatePointer blitState = std::make_shared<gpu::State>();

    blitState->setDepthTest(gpu::State::DepthTest(false, false));
    blitState->setColorWriteMask(true, true, true, true);

    _pipeline = gpu::PipelinePointer(gpu::Pipeline::create(gpu::Shader::createProgram(toneMapping), blitState));
    _mirrorPipeline = gpu::PipelinePointer(gpu::Pipeline::create(gpu::Shader::createProgram(toneMapping_mirrored), blitState));
#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)
    // SRGB with zero exposure is an exact no-op.  Avoid Apple's software GL
    // miscompile of the larger tone-mapping fragment shader for that common
    // case, while retaining the same viewport-driven texture coordinates.
    const auto passthroughVertex = gpu::Shader::createVertex(
        shader::gpu::vertex::DrawViewportQuadTransformTexcoord);
    _passthroughPipeline = gpu::PipelinePointer(gpu::Pipeline::create(
        gpu::Shader::createProgram(passthroughVertex,
            gpu::Shader::createPixel(shader::gpu::fragment::DrawTextureOpaque)),
        blitState));
    _mirrorPassthroughPipeline = gpu::PipelinePointer(gpu::Pipeline::create(
        gpu::Shader::createProgram(passthroughVertex,
            gpu::Shader::createPixel(shader::gpu::fragment::DrawTextureMirroredX)),
        blitState));
#endif
}

void ToneMapAndResample::setExposure(float exposure) {
    if (_exposure != exposure) {
        _exposure = exposure;
        _parametersBuffer.edit<Parameters>()._exposureRegister.fill(pow(2.0, exposure));
    }
}

void ToneMapAndResample::setCurve(TonemappingCurve curve) {
    auto& params = _parametersBuffer.get<Parameters>();
    if (params._curveRegister.front() != (int)curve) {
        _parametersBuffer.edit<Parameters>()._curveRegister.fill((int)curve);
    }
}

void ToneMapAndResample::configure(const Config& config) {
    _debug = config.debug;
    _debugExposure = config.exposure;
    _debugCurve = (TonemappingCurve)config.curve;
}

void ToneMapAndResample::run(const RenderContextPointer& renderContext, const Input& input, Output& output) {
    assert(renderContext->args);
    assert(renderContext->args->hasViewFrustum());

    RenderArgs* args = renderContext->args;

    auto lightingBuffer = input.get0()->getRenderBuffer(0);
#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)
    if (qEnvironmentVariableIsSet("OVERTE_MACOS_GL_DIAGNOSTICS")) {
        const std::lock_guard<std::mutex> guard(diagnosticMutex);
        diagnosticInputFramebuffer = input.get0();
    }
#endif
    auto destinationFramebuffer = input.get1();
    const auto tonemappingFrame = input.get2();

    const auto& tonemappingStage = renderContext->_scene->getStage<TonemappingStage>();
    graphics::TonemappingPointer tonemapping;
    if (tonemappingStage && tonemappingFrame->_elements.size()) {
        tonemapping = tonemappingStage->getElement(tonemappingFrame->_elements.front());
    }

    if (args->_mirrorDepth > 0) {
        setCurve(TonemappingCurve::SRGB);
        setExposure(0.0f);
    } else if (_debug) {
        setCurve(_debugCurve);
        setExposure(_debugExposure);
    } else if (tonemapping) {
        setCurve(tonemapping->getCurve());
        setExposure(tonemapping->getExposure());
    }

    if (!destinationFramebuffer) {
        destinationFramebuffer = args->_blitFramebuffer;
    }

    if (!lightingBuffer || !destinationFramebuffer) {
        return;
    }

#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)
    if (qEnvironmentVariableIsSet("OVERTE_MACOS_GL_DIAGNOSTICS")) {
        std::call_once(diagnosticParametersOnce, [&] {
            const auto& parameters = _parametersBuffer.get<Parameters>();
            qInfo().noquote() << "OVERTE_MACOS_TONEMAP_PARAMS"
                              << "bytes=" << sizeof(Parameters)
                              << "exposure_scale=" << parameters._exposureRegister.front()
                              << "curve=" << parameters._curveRegister.front();
        });
    }
#endif

    if (!_pipeline) {
        init();
    }

#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)
    const auto& activeParameters = _parametersBuffer.get<Parameters>();
    const bool neutralPassthrough =
        activeParameters._curveRegister.front() == (int)TonemappingCurve::SRGB &&
        activeParameters._exposureRegister.front() == 1.0f;
    if (neutralPassthrough) {
        std::call_once(neutralPassthroughOnce, [] {
            qInfo().noquote() << "OVERTE_MACOS_TONEMAP_PASSTHROUGH"
                              << "curve=SRGB exposure=0";
        });
    }
#endif

    const auto bufferSize = destinationFramebuffer->getSize();

    auto srcBufferSize = glm::ivec2(lightingBuffer->getDimensions());

    glm::ivec4 destViewport{ 0, 0, bufferSize.x, bufferSize.y };

    gpu::doInBatch("Resample::run", args->_context, [&](gpu::Batch& batch) {
        batch.enableStereo(false);
        batch.setFramebuffer(destinationFramebuffer);

        batch.setViewportTransform(destViewport);
        batch.setProjectionTransform(glm::mat4());
        batch.resetViewTransform();
        bool shouldMirror = args->_numMirrorFlips >= (args->_renderMode != RenderArgs::MIRROR_RENDER_MODE ? 1 : 0);
#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)
        if (neutralPassthrough) {
            batch.setPipeline(shouldMirror ? _mirrorPassthroughPipeline : _passthroughPipeline);
        } else
#endif
        {
            batch.setPipeline(shouldMirror ? _mirrorPipeline : _pipeline);
        }

        batch.setModelTransform(gpu::Framebuffer::evalSubregionTexcoordTransform(srcBufferSize, args->_viewport));
#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)
        if (!neutralPassthrough)
#endif
        {
            batch.setUniformBuffer(render_utils::slot::buffer::ToneMappingParams, _parametersBuffer);
        }
        batch.setResourceTexture(render_utils::slot::texture::ToneMappingColor, lightingBuffer);
        batch.draw(gpu::TRIANGLE_STRIP, 4);
    });

    // Set full final viewport
    args->_viewport = destViewport;

    output = destinationFramebuffer;
}
