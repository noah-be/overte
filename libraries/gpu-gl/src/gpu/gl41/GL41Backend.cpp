//
//  Created by Sam Gateau on 10/27/2014.
//  Copyright 2014 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//
#include "GL41Backend.h"

#include <algorithm>
#include <array>
#include <cstring>
#include <mutex>
#include <queue>
#include <list>
#include <functional>
#include <unordered_set>
#include <glm/gtc/type_ptr.hpp>
#include <QtCore/QCoreApplication>
#include <QtCore/QDebug>
#include <QtCore/QString>

#include <shared/GlobalAppProperties.h>

Q_LOGGING_CATEGORY(gpugl41logging, "hifi.gpu.gl41")

using namespace gpu;
using namespace gpu::gl41;

const std::string GL41Backend::GL41_VERSION { "GL41" };

void GL41Backend::draw(GLenum mode, uint32 numVertices, uint32 startVertex) {
    if (isStereo()) {
#ifdef GPU_STEREO_DRAWCALL_INSTANCED
        glDrawArraysInstanced(mode, startVertex, numVertices, 2);
#else
        setupStereoSide(0);
        glDrawArrays(mode, startVertex, numVertices);
        setupStereoSide(1);
        glDrawArrays(mode, startVertex, numVertices);
#endif
        _stats._DSNumTriangles += 2 * numVertices / 3;
        _stats._DSNumDrawcalls += 2;

    } else {
        glDrawArrays(mode, startVertex, numVertices);
        _stats._DSNumTriangles += numVertices / 3;
        _stats._DSNumDrawcalls++;
    }
    _stats._DSNumAPIDrawcalls++;

    (void)CHECK_GL_ERROR();
}

void GL41Backend::do_draw(const Batch& batch, size_t paramOffset) {
    Primitive primitiveType = (Primitive)batch._params[paramOffset + 2]._uint;
    GLenum mode = gl::PRIMITIVE_TO_GL[primitiveType];
    uint32 numVertices = batch._params[paramOffset + 1]._uint;
    uint32 startVertex = batch._params[paramOffset + 0]._uint;

#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)
    // Capture the real driver-visible state for the first tone-map draw.  CPU
    // values alone cannot prove that Apple's GL implementation sees the same
    // UBO range.  Keep this bounded, opt-in and free of paths/arguments.
    static thread_local std::unordered_set<GLuint> tracedToneMapPrograms;
    const auto application = QCoreApplication::instance();
    const bool diagnosticsEnabled = qEnvironmentVariableIsSet("OVERTE_MACOS_GL_DIAGNOSTICS") ||
        (application && application->property(hifi::properties::TEST).isValid());
    if (diagnosticsEnabled && tracedToneMapPrograms.count(_pipeline._program) == 0) {
        QString fragmentName;
        if (auto pipeline = acquire(_pipeline._pipeline)) {
            const auto& program = pipeline->getProgram();
            if (program) {
                const auto& shaders = program->getShaders();
                if (shaders.size() > Shader::PIXEL && shaders[Shader::PIXEL]) {
                    fragmentName = QString::fromStdString(shaders[Shader::PIXEL]->getSource().name);
                }
            }
        }
        if (fragmentName.contains("toneMapping", Qt::CaseInsensitive)) {
            tracedToneMapPrograms.insert(_pipeline._program);

            GLint drawFramebuffer { 0 };
            GLint drawBuffer { 0 };
            GLint viewport[4] { 0, 0, 0, 0 };
            GLint scissorBox[4] { 0, 0, 0, 0 };
            GLboolean colorMask[4] { GL_FALSE, GL_FALSE, GL_FALSE, GL_FALSE };
            glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &drawFramebuffer);
            glGetIntegerv(GL_DRAW_BUFFER0, &drawBuffer);
            glGetIntegerv(GL_VIEWPORT, viewport);
            glGetIntegerv(GL_SCISSOR_BOX, scissorBox);
            glGetBooleanv(GL_COLOR_WRITEMASK, colorMask);
            const auto framebufferStatus = glCheckFramebufferStatus(GL_DRAW_FRAMEBUFFER);

            GLint uniformBuffer { 0 };
            GLint genericUniformBuffer { 0 };
            GLint64 uniformOffset { 0 };
            GLint64 uniformSize { 0 };
            glGetIntegeri_v(GL_UNIFORM_BUFFER_BINDING, 0, &uniformBuffer);
            glGetInteger64i_v(GL_UNIFORM_BUFFER_START, 0, &uniformOffset);
            glGetInteger64i_v(GL_UNIFORM_BUFFER_SIZE, 0, &uniformSize);
            glGetIntegerv(GL_UNIFORM_BUFFER_BINDING, &genericUniformBuffer);

            std::array<uint32_t, 8> uniformWords {};
            if (uniformBuffer != 0 && uniformSize > 0) {
                glBindBuffer(GL_UNIFORM_BUFFER, uniformBuffer);
                const auto bytesToRead = std::min<GLint64>(uniformSize,
                    static_cast<GLint64>(sizeof(uniformWords)));
                glGetBufferSubData(GL_UNIFORM_BUFFER, uniformOffset, bytesToRead,
                    uniformWords.data());
                glBindBuffer(GL_UNIFORM_BUFFER, genericUniformBuffer);
            }
            float exposureRegisterX { 0.0f };
            float exposureRegisterY { 0.0f };
            std::memcpy(&exposureRegisterX, &uniformWords[0], sizeof(float));
            std::memcpy(&exposureRegisterY, &uniformWords[1], sizeof(float));

            GLint activeTexture { GL_TEXTURE0 };
            GLint texture2D { 0 };
            GLint textureInternalFormat { 0 };
            glGetIntegerv(GL_ACTIVE_TEXTURE, &activeTexture);
            glActiveTexture(GL_TEXTURE0);
            glGetIntegerv(GL_TEXTURE_BINDING_2D, &texture2D);
            if (texture2D != 0) {
                glGetTexLevelParameteriv(GL_TEXTURE_2D, 0, GL_TEXTURE_INTERNAL_FORMAT,
                    &textureInternalFormat);
            }
            glActiveTexture(activeTexture);

            qInfo().noquote()
                << "OVERTE_MACOS_TONEMAP_GL_STATE"
                << "program=" << _pipeline._program
                << "fbo=" << drawFramebuffer
                << "fbo_status=" << framebufferStatus
                << "draw_buffer=" << drawBuffer
                << "viewport=" << viewport[0] << viewport[1] << viewport[2] << viewport[3]
                << "scissor_enabled=" << glIsEnabled(GL_SCISSOR_TEST)
                << "scissor=" << scissorBox[0] << scissorBox[1] << scissorBox[2] << scissorBox[3]
                << "blend_enabled=" << glIsEnabled(GL_BLEND)
                << "framebuffer_srgb=" << glIsEnabled(GL_FRAMEBUFFER_SRGB)
                << "color_mask=" << colorMask[0] << colorMask[1] << colorMask[2] << colorMask[3]
                << "ubo=" << uniformBuffer
                << "ubo_offset=" << uniformOffset
                << "ubo_size=" << uniformSize
                << "ubo_exposure_x=" << exposureRegisterX
                << "ubo_exposure_y=" << exposureRegisterY
                << "ubo_curve_x=" << static_cast<int32_t>(uniformWords[4])
                << "ubo_curve_y=" << static_cast<int32_t>(uniformWords[5])
                << "texture=" << texture2D
                << "texture_format=" << textureInternalFormat;
            (void)CHECK_GL_ERROR();
        }
    }
#endif

    draw(mode, numVertices, startVertex);
}

void GL41Backend::do_drawIndexed(const Batch& batch, size_t paramOffset) {
    Primitive primitiveType = (Primitive)batch._params[paramOffset + 2]._uint;
    GLenum mode = gl::PRIMITIVE_TO_GL[primitiveType];
    uint32 numIndices = batch._params[paramOffset + 1]._uint;
    uint32 startIndex = batch._params[paramOffset + 0]._uint;

    GLenum glType = gl::ELEMENT_TYPE_TO_GL[_input._indexBufferType];
    
    auto typeByteSize = TYPE_SIZE[_input._indexBufferType];
    GLvoid* indexBufferByteOffset = reinterpret_cast<GLvoid*>(startIndex * typeByteSize + _input._indexBufferOffset);

#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)
    // Record only the first indexed draw per GL program on each render thread.
    // This identifies driver-side first-draw stalls without exposing command
    // lines, paths, environment contents, or unbounded per-frame diagnostics.
    static thread_local std::unordered_set<GLuint> tracedPrograms;
    const auto application = QCoreApplication::instance();
    const bool diagnosticsEnabled = qEnvironmentVariableIsSet("OVERTE_MACOS_GL_DIAGNOSTICS") ||
        (application && application->property(hifi::properties::TEST).isValid());
    const bool traceProgram = diagnosticsEnabled &&
        tracedPrograms.insert(_pipeline._program).second;
    if (traceProgram) {
        QString vertexName { "dynamic" };
        QString fragmentName { "dynamic" };
        uint32_t gpuProgram { 0 };
        if (auto pipeline = acquire(_pipeline._pipeline)) {
            const auto& program = pipeline->getProgram();
            if (program) {
                gpuProgram = program->getID();
                const auto& shaders = program->getShaders();
                if (shaders.size() > Shader::VERTEX && shaders[Shader::VERTEX]) {
                    vertexName = QString::fromStdString(shaders[Shader::VERTEX]->getSource().name);
                }
                if (shaders.size() > Shader::PIXEL && shaders[Shader::PIXEL]) {
                    fragmentName = QString::fromStdString(shaders[Shader::PIXEL]->getSource().name);
                }
            }
        }
        qInfo().noquote()
            << "OVERTE_MACOS_GL_DRAW begin"
            << "gl_program=" << _pipeline._program
            << "gpu_program=" << gpuProgram
            << "vertex=" << vertexName
            << "fragment=" << fragmentName
            << "indices=" << numIndices;
    }
#endif

    if (isStereo()) {
#ifdef GPU_STEREO_DRAWCALL_INSTANCED
        glDrawElementsInstanced(mode, numIndices, glType, indexBufferByteOffset, 2);
#else
        setupStereoSide(0);
        glDrawElements(mode, numIndices, glType, indexBufferByteOffset);
        setupStereoSide(1);
        glDrawElements(mode, numIndices, glType, indexBufferByteOffset);
#endif
        _stats._DSNumTriangles += 2 * numIndices / 3;
        _stats._DSNumDrawcalls += 2;
    } else {
        glDrawElements(mode, numIndices, glType, indexBufferByteOffset);
        _stats._DSNumTriangles += numIndices / 3;
        _stats._DSNumDrawcalls++;
    }
#if defined(Q_OS_MAC) && !defined(Q_OS_IOS)
    if (traceProgram) {
        qInfo().noquote()
            << "OVERTE_MACOS_GL_DRAW end"
            << "gl_program=" << _pipeline._program;
    }
#endif
    _stats._DSNumAPIDrawcalls++;

    (void) CHECK_GL_ERROR();
}

void GL41Backend::do_drawInstanced(const Batch& batch, size_t paramOffset) {
    GLint numInstances = batch._params[paramOffset + 4]._uint;
    Primitive primitiveType = (Primitive)batch._params[paramOffset + 3]._uint;
    GLenum mode = gl::PRIMITIVE_TO_GL[primitiveType];
    uint32 numVertices = batch._params[paramOffset + 2]._uint;
    uint32 startVertex = batch._params[paramOffset + 1]._uint;


    if (isStereo()) {
        GLint trueNumInstances = 2 * numInstances;

#ifdef GPU_STEREO_DRAWCALL_INSTANCED
        glDrawArraysInstanced(mode, startVertex, numVertices, trueNumInstances);
#else
        setupStereoSide(0);
        glDrawArraysInstanced(mode, startVertex, numVertices, numInstances);
        setupStereoSide(1);
        glDrawArraysInstanced(mode, startVertex, numVertices, numInstances);
#endif
        _stats._DSNumTriangles += (trueNumInstances * numVertices) / 3;
        _stats._DSNumDrawcalls += trueNumInstances;
    } else {
        glDrawArraysInstanced(mode, startVertex, numVertices, numInstances);
        _stats._DSNumTriangles += (numInstances * numVertices) / 3;
        _stats._DSNumDrawcalls += numInstances;
    }
    _stats._DSNumAPIDrawcalls++;

    (void) CHECK_GL_ERROR();
}

void glbackend_glDrawElementsInstancedBaseVertexBaseInstance(GLenum mode, GLsizei count, GLenum type, const GLvoid *indices, GLsizei primcount, GLint basevertex, GLuint baseinstance) {
#if (GPU_INPUT_PROFILE == GPU_CORE_43)
    glDrawElementsInstancedBaseVertexBaseInstance(mode, count, type, indices, primcount, basevertex, baseinstance);
#else
    glDrawElementsInstanced(mode, count, type, indices, primcount);
#endif
}

void GL41Backend::do_drawIndexedInstanced(const Batch& batch, size_t paramOffset) {
    GLint numInstances = batch._params[paramOffset + 4]._uint;
    GLenum mode = gl::PRIMITIVE_TO_GL[(Primitive)batch._params[paramOffset + 3]._uint];
    uint32 numIndices = batch._params[paramOffset + 2]._uint;
    uint32 startIndex = batch._params[paramOffset + 1]._uint;
    // FIXME glDrawElementsInstancedBaseVertexBaseInstance is only available in GL 4.3 
    // and higher, so currently we ignore this field
    uint32 startInstance = batch._params[paramOffset + 0]._uint;
    GLenum glType = gl::ELEMENT_TYPE_TO_GL[_input._indexBufferType];

    auto typeByteSize = TYPE_SIZE[_input._indexBufferType];
    GLvoid* indexBufferByteOffset = reinterpret_cast<GLvoid*>(startIndex * typeByteSize + _input._indexBufferOffset);
 
    if (isStereo()) {
        GLint trueNumInstances = 2 * numInstances;

#ifdef GPU_STEREO_DRAWCALL_INSTANCED
        glbackend_glDrawElementsInstancedBaseVertexBaseInstance(mode, numIndices, glType, indexBufferByteOffset, trueNumInstances, 0, startInstance);
#else
        setupStereoSide(0);
        glbackend_glDrawElementsInstancedBaseVertexBaseInstance(mode, numIndices, glType, indexBufferByteOffset, numInstances, 0, startInstance);
        setupStereoSide(1);
        glbackend_glDrawElementsInstancedBaseVertexBaseInstance(mode, numIndices, glType, indexBufferByteOffset, numInstances, 0, startInstance);
#endif

        _stats._DSNumTriangles += (trueNumInstances * numIndices) / 3;
        _stats._DSNumDrawcalls += trueNumInstances;
    } else {
        glbackend_glDrawElementsInstancedBaseVertexBaseInstance(mode, numIndices, glType, indexBufferByteOffset, numInstances, 0, startInstance);
        _stats._DSNumTriangles += (numInstances * numIndices) / 3;
        _stats._DSNumDrawcalls += numInstances;
    }

    _stats._DSNumAPIDrawcalls++;

    (void)CHECK_GL_ERROR();
}


void GL41Backend::do_multiDrawIndirect(const Batch& batch, size_t paramOffset) {
#if (GPU_INPUT_PROFILE == GPU_CORE_43)
    uint commandCount = batch._params[paramOffset + 0]._uint;
    GLenum mode = gl::PRIMITIVE_TO_GL[(Primitive)batch._params[paramOffset + 1]._uint];

    glMultiDrawArraysIndirect(mode, reinterpret_cast<GLvoid*>(_input._indirectBufferOffset), commandCount, (GLsizei)_input._indirectBufferStride);
    _stats._DSNumDrawcalls += commandCount;
    _stats._DSNumAPIDrawcalls++;

#else
    // FIXME implement the slow path
#endif
    (void)CHECK_GL_ERROR();

}

void GL41Backend::do_multiDrawIndexedIndirect(const Batch& batch, size_t paramOffset) {
#if (GPU_INPUT_PROFILE == GPU_CORE_43)
    uint commandCount = batch._params[paramOffset + 0]._uint;
    GLenum mode = gl::PRIMITIVE_TO_GL[(Primitive)batch._params[paramOffset + 1]._uint];
    GLenum indexType = gl::ELEMENT_TYPE_TO_GL[_input._indexBufferType];
  
    glMultiDrawElementsIndirect(mode, indexType, reinterpret_cast<GLvoid*>(_input._indirectBufferOffset), commandCount, (GLsizei)_input._indirectBufferStride);
    _stats._DSNumDrawcalls += commandCount;
    _stats._DSNumAPIDrawcalls++;
#else
    // FIXME implement the slow path
#endif
    (void)CHECK_GL_ERROR();
}
