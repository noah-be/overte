// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include <QtTest/QtTest>
#include <QFile>
#include <graphics/SkinningPalette.h>
#include <Model.h>
#include <AnimSkeleton.h>
#include <GLTFSerializer.h>
#include <ResourceManager.h>
#include <model-baker/Baker.h>
#include <MeshPartPayload.h>
#include <CauterizedMeshPartPayload.h>
#include <RenderableModelEntityItem.h>
#include "SkinningFixtures.h"
#include <glm/gtc/type_ptr.hpp>
#include <cmath>
#include <limits>
#ifdef Q_OS_LINUX
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <glad/glad.h>
#endif

namespace {
// Populate the same mesh slots as ModelCache, without downloads or materials.
class OfflineGeometry : public Geometry {
public:
    explicit OfflineGeometry(const HFMModel::Pointer& hfm) {
        _hfmModel = hfm;
        auto meshes = std::make_shared<GeometryMeshes>();
        for (const auto& mesh : hfm->meshes) { meshes->push_back(mesh._mesh); }
        _meshes = meshes;
        _meshParts = std::make_shared<GeometryMeshParts>();
    }
};
class RuntimeModel : public Model {
public:
    explicit RuntimeModel(const HFMModel::Pointer& hfm) {
        _offset = glm::vec3(0);
        _renderGeometry = std::make_shared<OfflineGeometry>(hfm);
        updateGeometry(); // Real Rig initialization and per-mesh state allocation.
    }
    void refresh(bool dq) {
        setUseDualQuaternionSkinning(dq);
        _needsUpdateClusterMatrices = true;
        updateClusterMatrices(); // Real skeleton bind lookup and palette update.
    }
};
class OfflineCollisionEntity : public RenderableModelEntityItem {
public:
    explicit OfflineCollisionEntity(const ModelPointer& model) : RenderableModelEntityItem(QUuid::createUuid(), true) {
        setModel(model);
        // No URL/network request: the supplied model already has loaded geometry
        // and initialized joint states, so updateModelBounds need not simulate it.
    }
};
}

class ShaderSkinningTests : public QObject {
    Q_OBJECT
#ifdef Q_OS_LINUX
    EGLDisplay display{ EGL_NO_DISPLAY };
    EGLContext context{ EGL_NO_CONTEXT };
    EGLSurface surface{ EGL_NO_SURFACE };
    bool glReady { false };
    GLuint programs[2]{};
    GLuint vao{}, uniformBuffer{}, feedbackBuffer{}, vertexBuffer{};
    std::array<float, 10> output{};

    void evaluate(bool dq, const gpu::BufferPointer& palette, glm::uvec4 indices, glm::vec4 weights,
                  glm::vec4 position = {1,2,3,1}, glm::vec3 normal = {0,1,0}, int vertex = 0) {
        QVERIFY(palette);
        GLuint program = programs[dq ? 1 : 0];
        glUseProgram(program);
        glBindVertexArray(vao);
        glVertexAttribI4uiv(0, glm::value_ptr(indices));
        glVertexAttrib4fv(1, glm::value_ptr(weights));
        glUniform4fv(glGetUniformLocation(program, "testInputPosition"), 1, glm::value_ptr(position));
        glUniform3fv(glGetUniformLocation(program, "testInputNormal"), 1, glm::value_ptr(normal));
        glBindBuffer(GL_UNIFORM_BUFFER, uniformBuffer);
        glBufferData(GL_UNIFORM_BUFFER, palette->getSize(), palette->getData(), GL_DYNAMIC_DRAW);
        glBindBufferBase(GL_UNIFORM_BUFFER, GRAPHICS_BUFFER_SKINNING, uniformBuffer);
        glBindVertexArray(vao);
        glBindBuffer(GL_TRANSFORM_FEEDBACK_BUFFER, feedbackBuffer);
        glBufferData(GL_TRANSFORM_FEEDBACK_BUFFER, sizeof(output), nullptr, GL_DYNAMIC_READ);
        glBindBufferBase(GL_TRANSFORM_FEEDBACK_BUFFER, 0, feedbackBuffer);
        glEnable(GL_RASTERIZER_DISCARD);
        glBeginTransformFeedback(GL_POINTS);
        glDrawArrays(GL_POINTS, vertex, 1);
        glEndTransformFeedback();
        glDisable(GL_RASTERIZER_DISCARD);
        glGetBufferSubData(GL_TRANSFORM_FEEDBACK_BUFFER, 0, sizeof(output), output.data());
        QCOMPARE(glGetError(), GLenum(GL_NO_ERROR));
        for (float value : output) { QVERIFY(std::isfinite(value)); }
    }
    void expect(const std::array<float, 10>& wanted) {
        for (size_t i = 0; i < output.size(); ++i) {
            QVERIFY2(std::abs(output[i] - wanted[i]) < 0.0002f,
                     qPrintable(QString("component %1: actual %2, expected %3").arg(i).arg(output[i]).arg(wanted[i])));
        }
    }
#endif
private slots:
    void initTestCase() {
        DependencyManager::set<ResourceManager>(false);
        DependencyManager::set<ModelBlender>();
#ifdef Q_OS_LINUX
        // Native CI uses a software surfaceless context; no display/device service.
        qputenv("LIBGL_ALWAYS_SOFTWARE", "1");
        qputenv("EGL_PLATFORM", "surfaceless");
        qputenv("LP_NUM_THREADS", "2");
        display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
        EGLint major{}, minor{};
        QVERIFY2(eglInitialize(display, &major, &minor), "Software surfaceless EGL initialization is a required test prerequisite");
        QVERIFY(eglBindAPI(EGL_OPENGL_API));
        const EGLint configAttributes[]{ EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_BIT,
                                        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_NONE };
        EGLConfig config{};
        EGLint count{};
        QVERIFY(eglChooseConfig(display, configAttributes, &config, 1, &count));
        QVERIFY(count > 0);
        const EGLint contextAttributes[]{ EGL_CONTEXT_MAJOR_VERSION_KHR, 4, EGL_CONTEXT_MINOR_VERSION_KHR, 5,
            EGL_CONTEXT_OPENGL_PROFILE_MASK_KHR, EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT_KHR, EGL_NONE };
        context = eglCreateContext(display, config, EGL_NO_CONTEXT, contextAttributes);
        QVERIFY2(context != EGL_NO_CONTEXT, "Software OpenGL 4.5 is required for the production shader regression");
        const EGLint surfaceAttributes[]{ EGL_WIDTH, 1, EGL_HEIGHT, 1, EGL_NONE };
        surface = eglCreatePbufferSurface(display, config, surfaceAttributes);
        QVERIFY(surface != EGL_NO_SURFACE);
        QVERIFY(eglMakeCurrent(display, surface, surface, context));
        QVERIFY(gladLoadGLLoader(reinterpret_cast<GLADloadproc>(eglGetProcAddress)));
        glReady = true;
        qInfo() << "Shader execution renderer:" << reinterpret_cast<const char*>(glGetString(GL_RENDERER));
        for (int dq = 0; dq < 2; ++dq) {
            QFile source(QString(TEST_SHADER_DIR) + QString("/skinning-%1.vert").arg(dq));
            QVERIFY(source.open(QIODevice::ReadOnly));
            QByteArray text = source.readAll();
            const char* data = text.constData();
            GLuint shader = glCreateShader(GL_VERTEX_SHADER);
            glShaderSource(shader, 1, &data, nullptr);
            glCompileShader(shader);
            GLint success{};
            glGetShaderiv(shader, GL_COMPILE_STATUS, &success);
            char log[4096]{};
            glGetShaderInfoLog(shader, sizeof(log), nullptr, log);
            QVERIFY2(success, log);
            programs[dq] = glCreateProgram();
            glAttachShader(programs[dq], shader);
            const char* varyings[]{ "testPosition", "testNormal", "testTangent" };
            glTransformFeedbackVaryings(programs[dq], 3, varyings, GL_INTERLEAVED_ATTRIBS);
            glLinkProgram(programs[dq]);
            glGetProgramiv(programs[dq], GL_LINK_STATUS, &success);
            glGetProgramInfoLog(programs[dq], sizeof(log), nullptr, log);
            glDeleteShader(shader);
            QVERIFY2(success, log);
            GLuint block = glGetUniformBlockIndex(programs[dq], "skinClusterBuffer");
            QVERIFY(block != GL_INVALID_INDEX);
            GLint bytes{};
            glGetActiveUniformBlockiv(programs[dq], block, GL_UNIFORM_BLOCK_DATA_SIZE, &bytes);
            QCOMPARE(bytes, int(sizeof(graphics::SkinningPalette)));
            glUniformBlockBinding(programs[dq], block, GRAPHICS_BUFFER_SKINNING);
        }
        glGenVertexArrays(1, &vao);
        glGenBuffers(1, &uniformBuffer);
        glGenBuffers(1, &feedbackBuffer);
        glGenBuffers(1, &vertexBuffer);
#else
        QSKIP("The deterministic software EGL native lane is Linux-only");
#endif
    }
    void validMatrixAndDQAnimation() {
#ifdef Q_OS_LINUX
        const glm::quat rotation = glm::angleAxis(glm::radians(90.0f), glm::vec3(0,0,1));
        Model::TransformDualQuaternion dq(glm::vec3(2,3,4), rotation, glm::vec3(3,0,0));
        gpu::BufferPointer palette;
        QVERIFY(graphics::updateSkinningPalette(palette, std::vector<glm::mat4>{dq.getMatrix()}, 1));
        evaluate(false, palette, {0,128,65535,127}, {1,0,0,0});
        expect({-3,2,12,1, -3,0,0, 0,2,0});
        QVERIFY(graphics::updateSkinningPalette(palette, std::vector<Model::TransformDualQuaternion>{dq}, 1));
        evaluate(true, palette, {65535,0,128,127}, {0,1,0,0});
        expect({-3,2,12,1, -1,0,0, 0,1,0});
        dq.setCauterizationParameters(1.0f, {7,8,9});
        QVERIFY(graphics::updateSkinningPalette(palette, std::vector<Model::TransformDualQuaternion>{dq}, 1));
        evaluate(true, palette, {65535,0,128,127}, {0,1,0,0});
        expect({7,8,9,1, -1,0,0, 0,1,0});
#endif
    }
    void actualCountAndFiniteFallbacks() {
#ifdef Q_OS_LINUX
        const std::array<float,10> unchanged{1,2,3,1, 0,1,0, 1,0,0};
        gpu::BufferPointer palette;
        Model::TransformDualQuaternion dq(glm::vec3(1), glm::quat(1,0,0,0), glm::vec3(5,0,0));
        QVERIFY(graphics::updateSkinningPalette(palette, std::vector<Model::TransformDualQuaternion>{dq,dq}, 2));
        for (bool dual : {false,true}) {
            if (!dual) { QVERIFY(graphics::updateSkinningPalette(palette, std::vector<glm::mat4>{dq.getMatrix(),dq.getMatrix()}, 2)); }
            else { QVERIFY(graphics::updateSkinningPalette(palette, std::vector<Model::TransformDualQuaternion>{dq,dq}, 2)); }
            evaluate(dual, palette, {65535,128,127,2}, {1,1,1,1});
            expect(unchanged);
            evaluate(dual, palette, {65535,128,127,2}, {0,0,0,0});
            expect(unchanged);
            evaluate(dual, palette, {0,0,0,0}, {std::numeric_limits<float>::quiet_NaN(),
                std::numeric_limits<float>::infinity(), -1, 0});
            expect(unchanged);
            evaluate(dual, palette, {65535,1,128,127}, {0,1,0,0});
            expect({6,2,3,1, 0,1,0, 1,0,0});
            if (!dual) { QVERIFY(graphics::updateSkinningPalette(palette, std::vector<glm::mat4>{dq.getMatrix()}, 1)); }
            else { QVERIFY(graphics::updateSkinningPalette(palette, std::vector<Model::TransformDualQuaternion>{dq}, 1)); }
            evaluate(dual, palette, {1,128,65535,127}, {1,0,0,0});
            expect(unchanged); // Must not load padded/stale entry 1 after shrinking.
            QVERIFY(graphics::updateSkinningPalette(palette, std::vector<glm::mat4>{}, 0));
            evaluate(dual, palette, {0,127,128,65535}, {1,0,0,0});
            expect(unchanged);
        }
        Model::TransformDualQuaternion degenerate(glm::vec3(1), glm::quat(0,0,0,0), glm::vec3(0));
        QVERIFY(graphics::updateSkinningPalette(palette, std::vector<Model::TransformDualQuaternion>{degenerate}, 1));
        evaluate(true, palette, {0,128,65535,127}, {1,0,0,0});
        expect(unchanged);
#endif
    }
    void fullPaletteBoundaryAndPolarity() {
#ifdef Q_OS_LINUX
        gpu::BufferPointer palette;
        Model::TransformDualQuaternion a(glm::vec3(1), glm::quat(1,0,0,0), glm::vec3(3,0,0));
        Model::TransformDualQuaternion b(glm::vec3(1), glm::quat(-1,0,0,0), glm::vec3(5,0,0));
        std::vector<glm::mat4> matrices(128, glm::mat4(1));
        matrices[127] = a.getMatrix();
        QVERIFY(graphics::updateSkinningPalette(palette, matrices, 128));
        evaluate(false, palette, {127,128,65535,0}, {1,0,0,0});
        expect({4,2,3,1, 0,1,0, 1,0,0});
        std::vector<Model::TransformDualQuaternion> dqs(128, a);
        QVERIFY(graphics::updateSkinningPalette(palette, dqs, 128));
        evaluate(true, palette, {127,128,65535,0}, {1,0,0,0});
        expect({4,2,3,1, 0,1,0, 1,0,0});
        QVERIFY(graphics::updateSkinningPalette(palette, std::vector<Model::TransformDualQuaternion>{a,b}, 2));
        evaluate(true, palette, {65535,1,0,128}, {0,.5f,.5f,0});
        expect({5,2,3,1, 0,1,0, 1,0,0});
        QVERIFY(!graphics::updateSkinningPalette(palette, std::vector<glm::mat4>{glm::mat4(1)}, 2));
        QVERIFY(!palette);
        QVERIFY(!graphics::updateSkinningPalette(palette, std::vector<glm::mat4>(129, glm::mat4(1)), 129));
        QVERIFY(!palette);
#endif
    }

    void importedPackedAnimation() {
#ifdef Q_OS_LINUX
        GLTFSerializer serializer;
        auto model = serializer.read(skinning_test::smallSkinInLargeScene(), {}, QUrl("file:///shader-control.gltf"));
        QVERIFY(model);
        baker::Baker bake(model, {}, QUrl()); bake.run();
        const auto& mesh = bake.getHFMModel()->meshes[0];
        QVERIFY(mesh._mesh);
        QCOMPARE(mesh.clusters.size(), 2);
        AnimSkeleton skeleton(*bake.getHFMModel());
        const auto& streams = mesh._mesh->getVertexStream();
        const auto indexAttribute = mesh._mesh->getVertexFormat()->getAttribute(gpu::Stream::SKIN_CLUSTER_INDEX);
        const auto weightAttribute = mesh._mesh->getVertexFormat()->getAttribute(gpu::Stream::SKIN_CLUSTER_WEIGHT);
        QCOMPARE(indexAttribute._channel, weightAttribute._channel);
        const size_t channel = indexAttribute._channel;
        glBindVertexArray(vao);
        glBindBuffer(GL_ARRAY_BUFFER, vertexBuffer);
        glBufferData(GL_ARRAY_BUFFER, streams.getBuffers()[channel]->getSize(), streams.getBuffers()[channel]->getData(), GL_STATIC_DRAW);
        glVertexAttribIPointer(0, 4, GL_UNSIGNED_BYTE, streams.getStrides()[channel],
            reinterpret_cast<void*>(size_t(streams.getOffsets()[channel]) + indexAttribute._offset));
        glVertexAttribPointer(1, 4, GL_UNSIGNED_SHORT, GL_TRUE, streams.getStrides()[channel],
            reinterpret_cast<void*>(size_t(streams.getOffsets()[channel]) + weightAttribute._offset));
        glEnableVertexAttribArray(0); glEnableVertexAttribArray(1);
        for (bool animated : {false,true}) {
            std::vector<glm::mat4> matrices;
            std::vector<Model::TransformDualQuaternion> dqs;
            for (int clusterIndex = 0; clusterIndex < mesh.clusters.size(); ++clusterIndex) {
                const auto cluster = skeleton.getClusterBindMatricesOriginalValues(0, clusterIndex);
                auto pose = skeleton.getAbsoluteDefaultPoses()[cluster.jointIndex];
                if (animated) { pose.trans().x += clusterIndex == 0 ? 2.0f : 6.0f; }
                matrices.emplace_back(glm::mat4(pose) * cluster.inverseBindMatrix);
                Transform jointTransform(pose.rot(), pose.scale(), pose.trans()), clusterTransform;
                Transform::mult(clusterTransform, jointTransform, cluster.inverseBindTransform);
                dqs.emplace_back(clusterTransform);
            }
            for (bool dual : {false,true}) {
                gpu::BufferPointer palette;
                if (dual) { QVERIFY(graphics::updateSkinningPalette(palette, dqs, mesh.clusters.size())); }
                else { QVERIFY(graphics::updateSkinningPalette(palette, matrices, mesh.clusters.size())); }
                for (int vertex = 0; vertex < 3; ++vertex) {
                    glm::vec4 point(mesh.vertices[vertex], 1.0f);
                    evaluate(dual, palette, {}, {}, point, {0,0,1}, vertex);
                    if (animated) { point.x += vertex == 0 ? 2.0f : (vertex == 1 ? 6.0f : 4.0f); }
                    expect({point.x,point.y,point.z,1, 0,0,1, 1,0,0});
                }
            }
        }
        glDisableVertexAttribArray(0); glDisableVertexAttribArray(1);
#endif
    }
    void mixedFallbackBounds_data() {
        QTest::addColumn<bool>("dq");
        QTest::newRow("matrix") << false;
        QTest::newRow("dual-quaternion") << true;
    }
    void mixedFallbackBounds() {
        QFETCH(bool, dq);
        auto doc = QJsonDocument::fromJson(skinning_test::smallSkinInLargeScene()).object();
        auto buffers = doc["buffers"].toArray();
        auto buffer = buffers[0].toObject();
        const auto uri = buffer["uri"].toString().toLatin1();
        auto binary = QByteArray::fromBase64(uri.mid(uri.indexOf(',') + 1));
        const auto weights = doc["accessors"].toArray()[4].toObject();
        const auto view = doc["bufferViews"].toArray()[weights["bufferView"].toInt()].toObject();
        std::memset(binary.data() + view["byteOffset"].toInt(), 0, 4 * sizeof(float));
        buffer["uri"] = "data:application/octet-stream;base64," + QString::fromLatin1(binary.toBase64());
        buffers[0] = buffer;
        doc["buffers"] = buffers;
        GLTFSerializer serializer;
        auto hfm = serializer.read(QJsonDocument(doc).toJson(QJsonDocument::Compact), {}, QUrl("file:///mixed-fallback.gltf"));
        QVERIFY(hfm);
        QCOMPARE(hfm->loadErrorCount, 0);
        baker::Baker bake(hfm, {}, QUrl()); bake.run();
        const auto& mesh = bake.getHFMModel()->meshes[0];
        QVERIFY(mesh._mesh);
        QCOMPARE(mesh.clusters.size(), 2);
        auto model = std::make_shared<RuntimeModel>(bake.getHFMModel());
        for (float displacement : {100.0f, -100.0f}) {
            for (const auto& cluster : mesh.clusters) {
                model->getRig().setJointTranslation(cluster.jointIndex, true,
                    hfm->joints[cluster.jointIndex].translation + glm::vec3(displacement, 0, 0), 1.0f);
            }
            model->getRig().updateAnimations(0, glm::mat4(1), glm::mat4(1));
            model->refresh(dq);
            const auto& state = model->getMeshState(0);
            for (int cluster = 0; cluster < mesh.clusters.size(); ++cluster) {
                const auto matrix = dq ? state.clusterDualQuaternions[cluster].getMatrix() : state.clusterMatrices[cluster];
                QVERIFY(std::abs(matrix[3].x - displacement) < 0.0002f);
            }
            Transform parent;
            parent.setTranslation(glm::vec3(0, 10, 0));
            ModelMeshPartPayload payload(model, 0, 0, 0, parent, 0);
            CauterizedMeshPartPayload cauterized(model, 0, 0, 0, parent, 0);
            const auto bound = payload.getBound(nullptr);
            const auto cautionBound = cauterized.getBound(nullptr);
            const auto fallback = mesh.vertices[0] + parent.getTranslation();
            qInfo() << "Mixed fallback bound:" << (dq ? "DQ" : "matrix") << "joint shift" << displacement
                    << "minimum x" << bound.getCorner().x << "contains fallback" << bound.contains(fallback);
            QVERIFY2(bound.contains(fallback), "Animated render bounds must contain the bind-space fallback vertex");
            QVERIFY(cautionBound.contains(fallback));
            for (int vertex : {1, 2}) {
                const auto animated = mesh.vertices[vertex] + glm::vec3(displacement, 10, 0);
                QVERIFY(bound.contains(animated));
                QVERIFY(cautionBound.contains(animated));
            }
#ifdef Q_OS_LINUX
            gpu::BufferPointer palette;
            if (dq) { QVERIFY(graphics::updateSkinningPalette(palette, state.clusterDualQuaternions, 2)); }
            else { QVERIFY(graphics::updateSkinningPalette(palette, state.clusterMatrices, 2)); }
            for (int vertex = 0; vertex < mesh.vertices.size(); ++vertex) {
                glm::uvec4 indices;
                glm::vec4 influences;
                for (int lane = 0; lane < 4; ++lane) {
                    indices[lane] = mesh.clusterIndices[vertex * 4 + lane];
                    influences[lane] = float(mesh.clusterWeights[vertex * 4 + lane]) / 65535.0f;
                }
                evaluate(dq, palette, indices, influences, glm::vec4(mesh.vertices[vertex], 1), mesh.normals[vertex]);
                const glm::vec3 rendered(output[0], output[1], output[2]);
                QVERIFY(bound.contains(rendered + parent.getTranslation()));
                QVERIFY(cautionBound.contains(rendered + parent.getTranslation()));
            }
#endif
        }
    }
    void collisionPreservesMeshSlots_data() {
        QTest::addColumn<int>("paletteCount");
        QTest::addColumn<int>("shapeType");
        QTest::newRow("valid-static-mesh") << 128 << int(SHAPE_TYPE_STATIC_MESH);
        QTest::newRow("rejected-first-static-mesh") << 129 << int(SHAPE_TYPE_STATIC_MESH);
        QTest::newRow("valid-simple-hull") << 128 << int(SHAPE_TYPE_SIMPLE_HULL);
        QTest::newRow("rejected-first-simple-hull") << 129 << int(SHAPE_TYPE_SIMPLE_HULL);
    }
    void collisionPreservesMeshSlots() {
        QFETCH(int, paletteCount);
        QFETCH(int, shapeType);
        auto doc = QJsonDocument::fromJson(skinning_test::manyUsedJoints(paletteCount)).object();
        auto nodes = doc["nodes"].toArray();
        auto rigid = nodes[199].toObject();
        rigid["mesh"] = 0; // A second mesh, translated +5, survives oversized skin rejection.
        nodes[199] = rigid;
        doc["nodes"] = nodes;
        GLTFSerializer serializer;
        auto hfm = serializer.read(QJsonDocument(doc).toJson(QJsonDocument::Compact), {}, QUrl("file:///collision-slots.gltf"));
        QVERIFY(hfm);
        QCOMPARE(hfm->meshes.size(), 2);
        baker::Baker bake(hfm, {}, QUrl()); bake.run();
        auto model = std::make_shared<RuntimeModel>(bake.getHFMModel());
        model->refresh(false);
        const bool rejected = paletteCount > 128;
        QCOMPARE(bool(hfm->meshes[0]._mesh), !rejected);
        QVERIFY(hfm->meshes[1]._mesh);
        QCOMPARE(hfm->meshes[1].clusters.size(), 1);
        QCOMPARE(model->getMeshState(1).clusterMatrices[0][3].x, 5.0f);
        OfflineCollisionEntity entity(model);
        entity.setShapeType(ShapeType(shapeType));
        QVERIFY(entity.isReadyToComputeShape());
        ShapeInfo shape;
        entity.computeShapeInfo(shape); // Actual production point and triangle extraction.
        QCOMPARE(int(shape.getType()), shapeType);
        QCOMPARE(shape.getPointCollection().size(), 1);
        const auto& points = shape.getPointCollection()[0];
        const int survivingVertices = hfm->meshes[1].vertices.size();
        QCOMPARE(points.size(), survivingVertices * (rejected ? 1 : 2));
        const int survivorOffset = rejected ? 0 : survivingVertices;
        qInfo() << "Collision survivor first x:" << points[survivorOffset].x << "expected 5, rejected first slot" << rejected;
        for (int vertex = 0; vertex < survivingVertices; ++vertex) {
            const auto expected = hfm->meshes[1].vertices[vertex] + glm::vec3(5, 0, 0);
            QVERIFY2(glm::length(points[survivorOffset + vertex] - expected) < 0.0002f,
                     "Surviving collision vertices must use their original mesh slot's transform");
            if (!rejected) { QVERIFY(glm::length(points[vertex] - hfm->meshes[0].vertices[vertex]) < 0.0002f); }
        }
        if (shapeType == SHAPE_TYPE_STATIC_MESH) {
            QCOMPARE(shape.getTriangleIndices().size(), points.size());
            for (int index : shape.getTriangleIndices()) { QVERIFY(index >= 0 && index < points.size()); }
        }
        for (bool dq : {false, true}) {
            model->refresh(dq);
            ModelMeshPartPayload rigidPayload(model, 1, 0, 0, Transform(), 0);
            const auto bound = rigidPayload.getBound(nullptr);
            QVERIFY(!bound.contains(hfm->meshes[1].vertices[0]));
            for (const auto& vertex : hfm->meshes[1].vertices) { QVERIFY(bound.contains(vertex + glm::vec3(5, 0, 0))); }
        }
    }
    void cleanupTestCase() {
#ifdef Q_OS_LINUX
        if (glReady) {
            glDeleteProgram(programs[0]); glDeleteProgram(programs[1]);
            glDeleteBuffers(1, &vertexBuffer);
            glDeleteBuffers(1, &feedbackBuffer); glDeleteBuffers(1, &uniformBuffer);
            glDeleteVertexArrays(1, &vao);
            eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
        }
        if (surface != EGL_NO_SURFACE) { eglDestroySurface(display, surface); }
        if (context != EGL_NO_CONTEXT) { eglDestroyContext(display, context); }
        if (display != EGL_NO_DISPLAY) { eglTerminate(display); }
#endif
    }
};
QTEST_GUILESS_MAIN(ShaderSkinningTests)
#include "ShaderSkinningTests.moc"
