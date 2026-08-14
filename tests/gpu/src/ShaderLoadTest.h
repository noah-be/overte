//
//  Created by Bradley Austin Davis on 2018/05/08
//  Copyright 2013-2018 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#pragma once

#include <cstdint>
#include <vector>

#include <QtTest/QtTest>

#include <gpu/Forward.h>
#include <gl/OffscreenGLCanvas.h>

class ShaderLoadTest : public QObject {
    Q_OBJECT

private:
    bool buildProgram(uint32_t programId);

private slots:
    void initTestCase();
    void cleanupTestCase();
    void testShaderLoad();

private:
    std::vector<uint32_t> _programs;
    OffscreenGLCanvas _canvas;
    gpu::ContextPointer _gpuContext;
};
