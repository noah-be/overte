//
//  ToneMapAndResample.h
//  libraries/render-utils/src
//
//  Created by Anna Brewer on 7/3/19.
//  Copyright 2019 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#ifndef hifi_ToneMapAndResample_h
#define hifi_ToneMapAndResample_h

#include <DependencyManager.h>
#include <NumericalConstants.h>
#include <QtCore/QtGlobal>

#include <array>
#include <cstddef>
#include <cstdint>

#include <gpu/Resource.h>
#include <gpu/Pipeline.h>
#include <render/Forward.h>
#include <render/DrawTask.h>

#include "TonemappingStage.h"

class ToneMappingConfig : public render::Job::Config {
    Q_OBJECT
    Q_PROPERTY(bool debug MEMBER debug WRITE setDebug NOTIFY dirty);
    Q_PROPERTY(int curve MEMBER curve WRITE setCurve NOTIFY dirty);
    Q_PROPERTY(float exposure MEMBER exposure WRITE setExposure NOTIFY dirty);

public:
    ToneMappingConfig() : render::Job::Config(true) {}

    void setDebug(bool newDebug) { debug = newDebug; emit dirty(); }
    void setCurve(int newCurve) { curve = std::max(0, std::min((int)TonemappingCurve::FILMIC, newCurve)); emit dirty(); }
    void setExposure(float newExposure) { exposure = newExposure; emit dirty(); }

    bool debug { false };
    int curve { (int)TonemappingCurve::SRGB };
    float exposure { 0.0f };

signals:
    void dirty();
};

class ToneMapAndResample {
public:
    ToneMapAndResample();
    virtual ~ToneMapAndResample() {}

    void setCurve(TonemappingCurve curve);
    void setExposure(float exposure);

    // Inputs: lightingFramebuffer, destinationFramebuffer, tonemappingFrame
    using Input = render::VaryingSet3<gpu::FramebufferPointer, gpu::FramebufferPointer, TonemappingStage::FramePointer>;
    using Output = gpu::FramebufferPointer;
    using Config = ToneMappingConfig;
    using JobModel = render::Job::ModelIO<ToneMapAndResample, Input, Output, Config>;

    void configure(const Config& config);
    void run(const render::RenderContextPointer& renderContext, const Input& input, Output& output);

protected:
    static gpu::PipelinePointer _pipeline;
    static gpu::PipelinePointer _mirrorPipeline;

    gpu::FramebufferPointer _destinationFrameBuffer;

private:
    float _exposure { 0.0f };

    bool _debug { false };
    TonemappingCurve _debugCurve { TonemappingCurve::SRGB };
    float _debugExposure { 0.0f };

    // Class describing the uniform buffer with all the parameters common to the tone mapping shaders
    class alignas(16) Parameters {
    public:
        // Keep each value replicated across a complete 16-byte register.
        // Apple's software OpenGL renderer binds and exposes the correct UBO
        // bytes but has returned sub-LSB results when a scalar is extracted
        // from this mixed float/int block. Vector consumption avoids that
        // driver path while preserving exposure and curve configurability.
        std::array<float, 4> _exposureRegister { 1.0f, 1.0f, 1.0f, 1.0f };
        std::array<std::int32_t, 4> _curveRegister {
            (std::int32_t)TonemappingCurve::SRGB,
            (std::int32_t)TonemappingCurve::SRGB,
            (std::int32_t)TonemappingCurve::SRGB,
            (std::int32_t)TonemappingCurve::SRGB
        };

        Parameters() {}
    };
    static_assert(sizeof(Parameters) == 32, "ToneMappingParams must occupy two std140 registers");
    static_assert(offsetof(Parameters, _exposureRegister) == 0, "Tone-map exposure must occupy register 0");
    static_assert(offsetof(Parameters, _curveRegister) == 16, "Tone-map curve must occupy register 1");

    typedef gpu::BufferView UniformBufferView;
    gpu::BufferView _parametersBuffer;

    void init();
};

#endif // hifi_ToneMapAndResample_h
