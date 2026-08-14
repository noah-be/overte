//
//  Created by Bradley Austin Davis on 2018/01/11
//  Copyright 2014 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0. See the accompanying
//  file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "ShaderLoadTest.h"

#include <atomic>

#include <QtCore/QElapsedTimer>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>

#include <SettingManager.h>
#include <gl/GLHelpers.h>
#include <gpu/Shader.h>
#include <gpu/gl/GLBackend.h>
#include <shaders/Shaders.h>
#include <test-utils/QTestExtensions.h>
#include <test-utils/Utils.h>

QTEST_MAIN(ShaderLoadTest)

extern std::atomic<size_t> gpuBinaryShadersLoaded;
extern const QString& getShaderCacheFile();

bool ShaderLoadTest::buildProgram(uint32_t programId) {
    // Assignment deliberately leaves the generated ID behind, producing a
    // dynamic shader object that cannot hide the binary-cache behavior behind
    // gpu::Shader's process-wide ID cache.
    shader::Source vertexSource;
    vertexSource = shader::Source::get(shader::getVertexId(programId));
    auto vertexShader = gpu::Shader::createVertex(vertexSource);

    shader::Source pixelSource;
    pixelSource = shader::Source::get(shader::getFragmentId(programId));
    auto pixelShader = gpu::Shader::createPixel(pixelSource);

    auto program = gpu::Shader::createProgram(vertexShader, pixelShader);
    auto backend = std::static_pointer_cast<gpu::gl::GLBackend>(_gpuContext->getBackend());
    backend->syncProgram(program);
    return !program->compilationHasFailed();
}

void ShaderLoadTest::initTestCase() {
    installTestMessageHandler();
    DependencyManager::set<Setting::Manager>();

    const auto& shaderCacheFile = getShaderCacheFile();
    if (QFileInfo(shaderCacheFile).exists()) {
        QVERIFY2(QFile(shaderCacheFile).remove(), "Unable to remove the pre-existing shader cache");
    }

    // Exercise a current generated production program rather than the retired
    // 2018 raw-GLSL cache fixture. Its source carries the same dialect,
    // variants and reflection data used by Interface.
    _programs = { shader::gpu::program::DrawTexture };

    getDefaultOpenGLSurfaceFormat();
    _canvas.create();
    if (!_canvas.makeCurrent()) {
        qFatal("Unable to make test GL context current");
    }
    gl::initModuleGl();
    gpu::Context::init<gpu::gl::GLBackend>();
    QVERIFY(_canvas.makeCurrent());
}

void ShaderLoadTest::cleanupTestCase() {
    if (_gpuContext) {
        _gpuContext->recycle();
        _gpuContext->shutdown();
        _gpuContext.reset();
    }
    DependencyManager::destroy<Setting::Manager>();
}

void ShaderLoadTest::testShaderLoad() {
    _gpuContext = std::make_shared<gpu::Context>();
    QCOMPARE(gpuBinaryShadersLoaded.load(), size_t { 0 });

    const size_t expectedBinaryLoads = _programs.size() * shader::allVariants().size();
    QElapsedTimer timer;

    // The first load must compile and populate the backend cache.
    timer.start();
    for (const auto programId : _programs) {
        QVERIFY(buildProgram(programId));
    }
    qDebug() << "Uncached shader load took" << timer.elapsed() << "ms";
    QCOMPARE(gpuBinaryShadersLoaded.load(), size_t { 0 });
    _gpuContext->recycle();
    glFinish();

    GLint binaryFormatCount { 0 };
    glGetIntegerv(GL_NUM_PROGRAM_BINARY_FORMATS, &binaryFormatCount);
    if (binaryFormatCount == 0) {
        QSKIP("The active OpenGL implementation does not expose program binaries");
    }

    // New dynamic program objects with the same generated sources must load
    // every variant from the in-memory program-binary cache.
    timer.restart();
    for (const auto programId : _programs) {
        QVERIFY(buildProgram(programId));
    }
    qDebug() << "In-memory cached shader load took" << timer.elapsed() << "ms";
    QCOMPARE(gpuBinaryShadersLoaded.load(), expectedBinaryLoads);

    // Shutting down persists the cache. A fresh backend must then read and use
    // those same program binaries from disk.
    gpuBinaryShadersLoaded = 0;
    _gpuContext->recycle();
    _gpuContext->shutdown();
    _gpuContext.reset();
    QVERIFY2(QFileInfo(getShaderCacheFile()).isFile(), "Shader cache was not persisted to disk");

    QVERIFY(_canvas.makeCurrent());
    _gpuContext = std::make_shared<gpu::Context>();
    timer.restart();
    for (const auto programId : _programs) {
        QVERIFY(buildProgram(programId));
    }
    qDebug() << "Disk-cached shader load took" << timer.elapsed() << "ms";
    QCOMPARE(gpuBinaryShadersLoaded.load(), expectedBinaryLoads);
}
