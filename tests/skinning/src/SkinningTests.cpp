// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include <QtTest/QtTest>
#include "SkinningFixtures.h"
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <GLTFSerializer.h>
#include <ResourceManager.h>
#include <model-baker/Baker.h>
#include <AnimSkeleton.h>
#include <FBXSerializer.h>
#include <FBXWriter.h>
#include <QBuffer>
#include <graphics/SkinningPalette.h>
#include <functional>
#include <cstring>
#include <limits>

namespace {
using skinning_test::smallSkinInLargeScene;

QByteArray editedGLTF(const std::function<void(QJsonObject&, QByteArray&)>& edit) {
    auto doc = QJsonDocument::fromJson(smallSkinInLargeScene()).object();
    auto buffers = doc["buffers"].toArray();
    auto object = buffers[0].toObject();
    auto uri = object["uri"].toString().toLatin1();
    auto binary = QByteArray::fromBase64(uri.mid(uri.indexOf(',') + 1));
    edit(doc, binary);
    object["uri"] = "data:application/octet-stream;base64," + QString::fromLatin1(binary.toBase64());
    object["byteLength"] = binary.size();
    buffers[0] = object;
    doc["buffers"] = buffers;
    return QJsonDocument(doc).toJson(QJsonDocument::Compact);
}
int attributeOffset(const QJsonObject& doc, int accessor) {
    auto entry = doc["accessors"].toArray()[accessor].toObject();
    return doc["bufferViews"].toArray()[entry["bufferView"].toInt()].toObject()["byteOffset"].toInt();
}
QByteArray asciiFBX(int clusters, bool malformed = false, bool invalidVertex = false, bool extraInfluences = false) {
    QByteArray objects = R"(FBXHeaderExtension: { FBXVersion: 7400 }
GlobalSettings: { Properties70: { P: "UnitScaleFactor", "double", "Number", "",100 } }
Objects: {
 Geometry: 1,"Geometry::Mesh","Mesh" {
  Vertices: *9 { a: 0,0,0,1,0,0,0,1,0 }
  PolygonVertexIndex: *3 { a: 0,1,-3 }
 }
 Model: 2,"Model::Mesh","Mesh" { }
 Deformer: 3,"Deformer::Skin","Skin" { }
)";
    QByteArray connections = "Connections: {\n C: \"OO\",1,2\n C: \"OO\",3,1\n C: \"OO\",2,0\n";
    for (int i = 0; i < clusters; ++i) {
        int joint = 1000 + i, cluster = 2000 + i;
        objects += " Model: " + QByteArray::number(joint) + ",\"Model::Joint" + QByteArray::number(i) + "\",\"LimbNode\" { }\n";
        objects += " Deformer: " + QByteArray::number(cluster) + ",\"Deformer::Cluster" + QByteArray::number(i) + "\",\"Cluster\" {\n";
        objects += "  Indexes: *1 { a: " + QByteArray::number(invalidVertex ? 65535 : (i == 1 ? 1 : 0)) + " }\n";
        objects += malformed ? "  Weights: *2 { a: 1,1 }\n" : "  Weights: *1 { a: " + QByteArray::number(extraInfluences || i < 2 ? 1 : 0) + " }\n";
        objects += "  TransformLink: *16 { a: 1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1 }\n }\n";
        connections += " C: \"OO\"," + QByteArray::number(cluster) + ",3\n";
        connections += " C: \"OO\"," + QByteArray::number(joint) + "," + QByteArray::number(cluster) + "\n";
        connections += " C: \"OO\"," + QByteArray::number(joint) + ",0\n";
    }
    return objects + "}\n" + connections + "}\n";
}
HFMMesh influenceMesh(int paletteCount, int vertices = 3) {
    HFMMesh mesh;
    mesh.modelTransform = glm::mat4(1.0f);
    mesh.vertices.fill(glm::vec3(1,2,3), vertices);
    mesh.normals.fill(glm::vec3(0,1,0), vertices);
    mesh.tangents.fill(glm::vec3(1,0,0), vertices);
    mesh.clusterIndices.fill(0, vertices * 4);
    mesh.clusterWeights.fill(0, vertices * 4);
    HFMMeshPart part;
    for (int i = 0; i < vertices; ++i) { part.triangleIndices.append(i); }
    mesh.parts.append(part);
    for (int index = 0; index < paletteCount; ++index) {
        HFMCluster cluster;
        cluster.jointIndex = index % 200;
        cluster.inverseBindMatrix = glm::translate(glm::mat4(1.0f), glm::vec3(-float(index),0,0));
        cluster.inverseBindTransform = Transform(cluster.inverseBindMatrix);
        mesh.clusters.append(cluster);
    }
    return mesh;
}
void checkPacking(const HFMMesh& mesh) {
    QVERIFY(mesh._mesh);
    auto format = mesh._mesh->getVertexFormat();
    const auto& streams = mesh._mesh->getVertexStream();
    auto indices = format->getAttribute(gpu::Stream::SKIN_CLUSTER_INDEX);
    auto weights = format->getAttribute(gpu::Stream::SKIN_CLUSTER_WEIGHT);
    QCOMPARE(indices.getSize(), uint32_t(4));
    QCOMPARE(weights.getSize(), uint32_t(8));
    for (int vertex = 0; vertex < mesh.vertices.size(); ++vertex) {
        const auto* i = streams.getBuffers()[indices._channel]->getData() + streams.getOffsets()[indices._channel]
            + indices._offset + vertex * streams.getStrides()[indices._channel];
        const auto* w = streams.getBuffers()[weights._channel]->getData() + streams.getOffsets()[weights._channel]
            + weights._offset + vertex * streams.getStrides()[weights._channel];
        for (int lane = 0; lane < 4; ++lane) {
            uint16_t packedWeight{};
            std::memcpy(&packedWeight, w + lane * 2, 2);
            QCOMPARE(uint16_t(i[lane]), mesh.clusterIndices[vertex * 4 + lane]);
            QCOMPARE(packedWeight, mesh.clusterWeights[vertex * 4 + lane]);
        }
    }
}

}

class SkinningTests : public QObject {
    Q_OBJECT
private slots:
    void initTestCase() { DependencyManager::set<ResourceManager>(false); }
    void compactImportedPalette() {
        GLTFSerializer serializer;
        auto model = serializer.read(smallSkinInLargeScene(), {}, QUrl("file:///offline-skin.gltf"));
        QVERIFY(model);
        QCOMPARE(model->loadErrorCount, 0);
        QCOMPARE(model->meshes.size(), 1);
        baker::Baker baker(model, {}, QUrl());
        baker.run();
        const auto& mesh = baker.getHFMModel()->meshes[0];
        QVERIFY(mesh._mesh);
        QCOMPARE(mesh.clusters.size(), 2);
        checkPacking(mesh);
        for (int lane = 0; lane < mesh.clusterIndices.size(); ++lane) {
            QVERIFY(mesh.clusterIndices[lane] < mesh.clusters.size());
        }
        QCOMPARE(model->joints[mesh.clusters[0].jointIndex].name, QString("node150"));
        QCOMPARE(model->joints[mesh.clusters[1].jointIndex].name, QString("node199"));
        QCOMPARE(mesh.clusters[0].inverseBindMatrix[3].x, -3.0f);
        QCOMPARE(mesh.clusters[1].inverseBindMatrix[3].x, -5.0f);
        AnimSkeleton skeleton(*baker.getHFMModel());
        QCOMPARE(skeleton.getClusterBindMatricesOriginalValues(0, 0).jointIndex, mesh.clusters[0].jointIndex);
        QCOMPARE(skeleton.getClusterBindMatricesOriginalValues(0, 1).inverseBindMatrix[3].x, -5.0f);
        // Real skeleton bind lookup preserves the neutral deformation after remap.
        for (int clusterIndex = 0; clusterIndex < 2; ++clusterIndex) {
            const auto cluster = skeleton.getClusterBindMatricesOriginalValues(0, clusterIndex);
            const auto bindPose = model->joints[cluster.jointIndex].transform * cluster.inverseBindMatrix;
            const auto point = bindPose * glm::vec4(1,2,3,1);
            QVERIFY(glm::length(point - glm::vec4(1,2,3,1)) < 0.0001f);
        }
    }
    void importedInactiveLanesAndZeroWeights() {
        GLTFSerializer serializer;
        auto bytes = editedGLTF([](QJsonObject& doc, QByteArray& binary) {
            const int offset = attributeOffset(doc, 3);
            const uint16_t invalid = 65535;
            for (int vertex = 0; vertex < 3; ++vertex) {
                std::memcpy(binary.data() + offset + vertex * 8 + 4, &invalid, 2);
            }
        });
        auto model = serializer.read(bytes, {}, QUrl("file:///inactive.gltf"));
        QVERIFY(model);
        QCOMPARE(model->loadErrorCount, 0);
        baker::Baker bake(model, {}, QUrl()); bake.run();
        checkPacking(bake.getHFMModel()->meshes[0]);
        bytes = editedGLTF([](QJsonObject& doc, QByteArray& binary) {
            std::memset(binary.data() + attributeOffset(doc, 4), 0, 3 * 4 * sizeof(float));
            const uint16_t invalid = 65535;
            for (int lane = 0; lane < 12; ++lane) {
                std::memcpy(binary.data() + attributeOffset(doc, 3) + lane * 2, &invalid, 2);
            }
        });
        GLTFSerializer zeroSerializer;
        auto zero = zeroSerializer.read(bytes, {}, QUrl("file:///zero.gltf"));
        QVERIFY(zero);
        QCOMPARE(zero->loadErrorCount, 0);
        baker::Baker zeroBake(zero, {}, QUrl()); zeroBake.run();
        const auto& mesh = zeroBake.getHFMModel()->meshes[0];
        QVERIFY(mesh.clusters.isEmpty());
        checkPacking(mesh);
        for (auto weight : mesh.clusterWeights) { QCOMPARE(weight, uint16_t(0)); }
    }
    void expandedAndHierarchicalSkin() {
        auto bytes = editedGLTF([](QJsonObject& doc, QByteArray&) {
            auto meshes = doc["meshes"].toArray(); auto mesh = meshes[0].toObject();
            auto primitives = mesh["primitives"].toArray(); auto primitive = primitives[0].toObject();
            auto attrs = primitive["attributes"].toObject(); attrs.remove("NORMAL");
            primitive["attributes"] = attrs; primitives[0] = primitive;
            mesh["primitives"] = primitives; meshes[0] = mesh; doc["meshes"] = meshes;
            auto nodes = doc["nodes"].toArray();
            auto parent = nodes[150].toObject(); parent["children"] = QJsonArray{199}; nodes[150] = parent;
            auto child = nodes[199].toObject(); child["translation"] = QJsonArray{2,0,0}; nodes[199] = child;
            doc["nodes"] = nodes;
        });
        GLTFSerializer serializer;
        auto model = serializer.read(bytes, {}, QUrl("file:///hierarchy.gltf"));
        QVERIFY(model);
        QCOMPARE(model->loadErrorCount, 0);
        baker::Baker bake(model, {}, QUrl()); bake.run();
        const auto& mesh = bake.getHFMModel()->meshes[0];
        QCOMPARE(mesh.clusters.size(), 2);
        checkPacking(mesh);
        AnimSkeleton skeleton(*bake.getHFMModel());
        for (int clusterIndex = 0; clusterIndex < 2; ++clusterIndex) {
            const auto cluster = skeleton.getClusterBindMatricesOriginalValues(0, clusterIndex);
            const auto point = glm::mat4(skeleton.getAbsoluteDefaultPoses()[cluster.jointIndex]) *
                cluster.inverseBindMatrix * glm::vec4(1,2,3,1);
            QVERIFY(glm::length(point - glm::vec4(1,2,3,1)) < 0.0001f);
        }
    }
    void malformedGLTF() {
        for (int attribute : {3,4}) {
            auto bytes = editedGLTF([&](QJsonObject& doc, QByteArray&) {
                auto accessors = doc["accessors"].toArray();
                auto entry = accessors[attribute].toObject(); entry["count"] = 2;
                accessors[attribute] = entry; doc["accessors"] = accessors;
            });
            GLTFSerializer serializer;
            QVERIFY(!serializer.read(bytes, {}, QUrl("file:///cardinality.gltf")));
        }
        for (int attribute : {3,4,5}) {
            auto bytes = editedGLTF([&](QJsonObject& doc, QByteArray&) {
                auto accessors = doc["accessors"].toArray();
                auto entry = accessors[attribute].toObject(); entry["type"] = "SCALAR";
                accessors[attribute] = entry; doc["accessors"] = accessors;
            });
            GLTFSerializer serializer;
            QVERIFY(!serializer.read(bytes, {}, QUrl("file:///representation.gltf")));
        }
        for (float value : {-1.0f, std::numeric_limits<float>::quiet_NaN(), std::numeric_limits<float>::infinity()}) {
            auto bytes = editedGLTF([&](QJsonObject& doc, QByteArray& binary) {
                std::memcpy(binary.data() + attributeOffset(doc, 4), &value, sizeof(value));
            });
            GLTFSerializer serializer;
            QVERIFY(!serializer.read(bytes, {}, QUrl("file:///invalid-weight.gltf")));
        }
        for (uint16_t index : {uint16_t(127), uint16_t(128), uint16_t(65535)}) {
            auto bytes = editedGLTF([&](QJsonObject& doc, QByteArray& binary) {
                std::memcpy(binary.data() + attributeOffset(doc, 3), &index, sizeof(index));
            });
            GLTFSerializer serializer;
            QVERIFY(!serializer.read(bytes, {}, QUrl("file:///invalid-joint.gltf")));
        }
        auto bytes = editedGLTF([](QJsonObject& doc, QByteArray&) {
            auto meshes = doc["meshes"].toArray(); auto mesh = meshes[0].toObject();
            auto primitives = mesh["primitives"].toArray(); auto primitive = primitives[0].toObject();
            auto attrs = primitive["attributes"].toObject(); attrs["JOINTS_1"] = 3; attrs["WEIGHTS_1"] = 4;
            primitive["attributes"] = attrs; primitives[0] = primitive;
            mesh["primitives"] = primitives; meshes[0] = mesh; doc["meshes"] = meshes;
        });
        GLTFSerializer extra;
        QVERIFY(!extra.read(bytes, {}, QUrl("file:///extra-influences.gltf")));
    }
    void distinctSkinBindsAndRigidNode() {
        auto bytes = editedGLTF([](QJsonObject& doc, QByteArray& binary) {
            const float bind[]{1,0,0,0,0,1,0,0,0,0,1,0,-7,0,0,1,
                               1,0,0,0,0,1,0,0,0,0,1,0,-9,0,0,1};
            auto views = doc["bufferViews"].toArray();
            views.append(QJsonObject{{"buffer",0},{"byteOffset",binary.size()},{"byteLength",int(sizeof(bind))}});
            binary.append(reinterpret_cast<const char*>(bind), sizeof(bind));
            auto accessors = doc["accessors"].toArray();
            accessors.append(QJsonObject{{"bufferView",views.size()-1},{"componentType",5126},{"type","MAT4"},{"count",2}});
            auto skins = doc["skins"].toArray();
            skins.append(QJsonObject{{"joints",QJsonArray{150,199}},{"inverseBindMatrices",accessors.size()-1}});
            auto nodes = doc["nodes"].toArray();
            auto second = nodes[1].toObject(); second["mesh"] = 0; second["skin"] = 1; nodes[1] = second;
            auto rigid = nodes[2].toObject(); rigid["mesh"] = 0; nodes[2] = rigid;
            doc["nodes"] = nodes; doc["skins"] = skins; doc["accessors"] = accessors; doc["bufferViews"] = views;
        });
        GLTFSerializer serializer;
        auto model = serializer.read(bytes, {}, QUrl("file:///multiple-skins.gltf"));
        QVERIFY(model);
        QCOMPARE(model->meshes.size(), 3);
        QCOMPARE(model->meshes[0].clusters[0].inverseBindMatrix[3].x, -3.0f);
        QCOMPARE(model->meshes[1].clusters[0].inverseBindMatrix[3].x, -7.0f);
        QCOMPARE(model->meshes[2].clusters.size(), 1);
        QVERIFY(model->meshes[2].clusterIndices.isEmpty());
        QVERIFY(model->joints[model->meshes[0].clusters[0].jointIndex].isSkeletonJoint);
        auto identityBytes = editedGLTF([](QJsonObject& doc, QByteArray&) {
            auto skins = doc["skins"].toArray(); auto skin = skins[0].toObject();
            skin.remove("inverseBindMatrices"); skins[0] = skin; doc["skins"] = skins;
        });
        GLTFSerializer identitySerializer;
        auto identity = identitySerializer.read(identityBytes, {}, QUrl("file:///identity-bind.gltf"));
        QVERIFY(identity);
        QCOMPARE(identity->meshes[0].clusters[0].inverseBindMatrix[3].x, 0.0f);
    }
    void paletteBoundariesAndBakerRejection() {
        for (int originalIndex : {127,128,65535}) {
            auto mesh = influenceMesh(originalIndex + 1);
            for (int vertex = 0; vertex < 3; ++vertex) {
                mesh.clusterIndices[vertex * 4] = uint16_t(originalIndex);
                mesh.clusterWeights[vertex * 4] = 65535;
                mesh.clusterIndices[vertex * 4 + 1] = 65535; // FBX-style unused root lane.
            }
            GLTFSerializer serializer;
            auto model = serializer.read(smallSkinInLargeScene(), {}, QUrl("file:///packing-boundary.gltf"));
            QVERIFY(model);
            model->meshes[0] = mesh;
            baker::Baker bake(model, {}, QUrl()); bake.run();
            const auto& packed = bake.getHFMModel()->meshes[0];
            QCOMPARE(model->loadErrorCount, 0);
            QCOMPARE(packed.clusters.size(), 1);
            QCOMPARE(packed.clusters[0].jointIndex, originalIndex % 200);
            QCOMPARE(packed.clusters[0].inverseBindMatrix[3].x, -float(originalIndex));
            for (auto index : packed.clusterIndices) { QCOMPARE(index, uint16_t(0)); }
            checkPacking(packed);
        }
        for (int malformed = 0; malformed < 8; ++malformed) {
            GLTFSerializer serializer;
            auto model = serializer.read(smallSkinInLargeScene(), {}, QUrl("file:///baker-control.gltf"));
            QVERIFY(model);
            auto mesh = influenceMesh(2);
            mesh.clusterWeights[0] = 65535;
            if (malformed == 0) { mesh.clusterIndices.removeLast(); }
            if (malformed == 1) { mesh.clusterWeights.removeLast(); }
            if (malformed == 2) { mesh.clusterIndices.resize(8); mesh.clusterWeights.resize(8); }
            if (malformed == 3) { mesh.clusterIndices[0] = 128; }
            if (malformed == 4) { mesh.clusters[0].jointIndex = 200; }
            if (malformed == 5) { mesh.clusters[0].inverseBindMatrix[0][0] = std::numeric_limits<float>::quiet_NaN(); }
            if (malformed == 6) { mesh.clusters[0].inverseBindTransform.setTranslation(glm::vec3(std::numeric_limits<float>::quiet_NaN())); }
            if (malformed == 7) { mesh.clusters[0].inverseBindMatrix[3][3] = 0.0f; }
            model->meshes[0] = mesh;
            baker::Baker bake(model, {}, QUrl());
            bake.getConfiguration()->getJobConfig("BuildDracoMesh")->setEnabled(true);
            bake.run();
            const auto& rejected = bake.getHFMModel()->meshes[0];
            QVERIFY(!rejected.skinningDataValid);
            QVERIFY(!rejected._mesh);
            QVERIFY(rejected.clusters.isEmpty());
            QVERIFY(rejected.parts.isEmpty());
            QVERIFY(model->loadErrorCount > 0);
            QCOMPARE(bake.getDracoErrors().size(), size_t(1));
            QVERIFY(bake.getDracoErrors()[0]);
            QVERIFY(bake.getDracoMeshes()[0].isEmpty());
        }
        auto oversized = influenceMesh(129,129);
        for (int vertex = 0; vertex < 129; ++vertex) {
            oversized.clusterIndices[vertex*4] = uint16_t(vertex);
            oversized.clusterWeights[vertex*4] = 65535;
        }
        QString error;
        QVERIFY(!oversized.prepareSkinningPalette(200,error));
        QVERIFY(error.contains("128"));
        QVERIFY(!oversized.skinningDataValid);
        QVERIFY(oversized.clusters.isEmpty());
        auto supported = influenceMesh(128,129);
        for (int vertex = 0; vertex < 129; ++vertex) {
            supported.clusterIndices[vertex*4] = uint16_t(vertex%128);
            supported.clusterWeights[vertex*4] = 65535;
        }
        QVERIFY(supported.prepareSkinningPalette(200,error));
        QCOMPARE(supported.clusters.size(),128);
    }
    void oversizedImportedPalette() {
        for (int count : {128,129}) {
            GLTFSerializer serializer;
            auto model = serializer.read(skinning_test::manyUsedJoints(count), {}, QUrl("file:///used-palette.gltf"));
            QVERIFY(model);
            QCOMPARE(model->meshes.size(),1);
            if (count == 129) {
                QVERIFY(model->loadErrorCount > 0);
                QVERIFY(!model->meshes[0].skinningDataValid);
                QVERIFY(model->meshes[0].parts.isEmpty());
            } else {
                QCOMPARE(model->loadErrorCount,0);
                QCOMPARE(model->meshes[0].clusters.size(),128);
            }
            baker::Baker bake(model,{},QUrl()); bake.run();
            const auto& mesh = bake.getHFMModel()->meshes[0];
            if (count == 129) { QVERIFY(!mesh._mesh); }
            else { checkPacking(mesh); }
        }
    }
    void offlineFBXRootAndMalformedCardinality() {
        FBXSerializer serializer;
        auto model = serializer.read(asciiFBX(128), {}, QUrl("file:///offline.fbx"));
        QVERIFY(model);
        QCOMPARE(model->meshes.size(),1);
        QCOMPARE(model->loadErrorCount,0);
        QCOMPARE(model->meshes[0].clusters.size(),3);
        baker::Baker bake(model,{},QUrl()); bake.run();
        checkPacking(bake.getHFMModel()->meshes[0]);
        FBXSerializer malformed;
        QVERIFY(!malformed.read(asciiFBX(2,true),{},QUrl("file:///malformed.fbx")));
        FBXSerializer extra;
        QVERIFY(!extra.read(asciiFBX(6,false,false,true),{},QUrl("file:///extra-influences.fbx")));
        FBXSerializer invalid;
        QVERIFY(!invalid.read(asciiFBX(2,false,true),{},QUrl("file:///invalid-vertex.fbx")));
    }
    void fbxRawSourceVertex_data() {
        QTest::addColumn<QByteArray>("rawIndex");
        QTest::addColumn<bool>("reject");
        QTest::newRow("zero-control") << QByteArray("0") << false;
        QTest::newRow("one-control") << QByteArray("1") << false;
        for (const auto& value : {"-1", "65535", "2147483648", "4294967296", "9223372036854775808",
                                  "18446744073709551616", "1.5", "nan", "inf", "invalid"}) {
            QTest::newRow(value) << QByteArray(value) << true;
        }
    }
    void fbxRawSourceVertex() {
        QFETCH(QByteArray, rawIndex);
        QFETCH(bool, reject);
        auto fixture = asciiFBX(1);
        fixture.replace("Indexes: *1 { a: 0 }", "Indexes: *1 { a: " + rawIndex + " }");
        FBXSerializer serializer;
        auto model = serializer.read(fixture, {}, QUrl("file:///raw-fbx-vertex.fbx"));
        qInfo() << "Raw FBX source vertex" << rawIndex << "accepted" << bool(model);
        if (reject) { QVERIFY2(!model, "Invalid raw FBX source vertex indices must be rejected before conversion"); }
        else {
            QVERIFY(model);
            QCOMPARE(model->loadErrorCount, 0);
            baker::Baker bake(model, {}, QUrl()); bake.run();
            const auto& mesh = bake.getHFMModel()->meshes[0];
            checkPacking(mesh);
            const int sourceVertex = rawIndex == "0" ? 0 : 1;
            QCOMPARE(mesh.clusterIndices[sourceVertex * 4], uint16_t(0));
            QVERIFY(mesh.clusterIndices[(sourceVertex == 0 ? 1 : 0) * 4] != 0);
        }
    }
    void fbxBinarySourceVertex_data() {
        QTest::addColumn<QVariant>("rawIndex");
        QTest::addColumn<bool>("reject");
        QTest::newRow("int-control") << QVariant(1) << false;
        QTest::newRow("int64-control") << QVariant::fromValue(qint64(1)) << false;
        QTest::newRow("int64-too-wide") << QVariant::fromValue(qint64(4294967296LL)) << true;
        QTest::newRow("float-control") << QVariant::fromValue(1.0f) << false;
        QTest::newRow("float-fraction") << QVariant::fromValue(1.5f) << true;
        QTest::newRow("double-fraction") << QVariant(1.5) << true;
        QTest::newRow("double-nan") << QVariant(std::numeric_limits<double>::quiet_NaN()) << true;
        QTest::newRow("double-infinity") << QVariant(std::numeric_limits<double>::infinity()) << true;
        QTest::newRow("int-array-control") << QVariant::fromValue(QVector<int>{1}) << false;
        QTest::newRow("int64-array-control") << QVariant::fromValue(QVector<qint64>{1}) << false;
        QTest::newRow("int64-array-too-wide") << QVariant::fromValue(QVector<qint64>{4294967296LL}) << true;
        QTest::newRow("float-array-control") << QVariant::fromValue(QVector<float>{1}) << false;
        QTest::newRow("float-array-fraction") << QVariant::fromValue(QVector<float>{1.5f}) << true;
        QTest::newRow("double-array-control") << QVariant::fromValue(QVector<double>{1}) << false;
        QTest::newRow("double-array-too-wide") << QVariant::fromValue(QVector<double>{4294967296.0}) << true;
        QTest::newRow("double-array-fraction") << QVariant::fromValue(QVector<double>{1.5}) << true;
    }
    void fbxBinarySourceVertex() {
        QFETCH(QVariant, rawIndex);
        QFETCH(bool, reject);
        auto text = asciiFBX(1);
        QBuffer input(&text);
        QVERIFY(input.open(QIODevice::ReadOnly));
        auto root = FBXSerializer::parseFBX(&input);
        bool edited = false;
        for (auto& objects : root.children) {
            if (objects.name != "Objects") { continue; }
            for (auto& deformer : objects.children) {
                if (deformer.name != "Deformer" || deformer.properties.last() != "Cluster") { continue; }
                for (auto& indices : deformer.children) {
                    if (indices.name != "Indexes") { continue; }
                    indices.children.clear();
                    indices.properties = {rawIndex};
                    edited = true;
                }
            }
        }
        QVERIFY(edited);
        // Real production writer and binary parser exercise scalar and array types.
        const auto fixture = FBXWriter::encodeFBX(root);
        FBXSerializer serializer;
        auto model = serializer.read(fixture, {}, QUrl("file:///binary-fbx-vertex.fbx"));
        if (reject) { QVERIFY2(!model, "Invalid binary FBX source vertex indices must be rejected before conversion"); }
        else {
            QVERIFY(model);
            QCOMPARE(model->loadErrorCount, 0);
            baker::Baker bake(model, {}, QUrl()); bake.run();
            const auto& mesh = bake.getHFMModel()->meshes[0];
            checkPacking(mesh);
            QCOMPARE(mesh.clusterIndices[4], uint16_t(0)); // Every binary control paints vertex 1.
            QVERIFY(mesh.clusterIndices[0] != 0);
            QVERIFY(mesh.clusterIndices[8] != 0);
        }
    }

};

QTEST_GUILESS_MAIN(SkinningTests)
#include "SkinningTests.moc"
