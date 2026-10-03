// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#ifndef overte_test_SkinningFixtures_h
#define overte_test_SkinningFixtures_h
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <cstdint>
#include <vector>
namespace skinning_test {
// Entirely embedded, deterministic glTF: two joints among 200 nodes, with
// distinct nonidentity bind transforms and no external resources.
inline QByteArray smallSkinInLargeScene() {
    QByteArray buffer;
    QJsonArray views, accessors;
    auto accessor = [&](const void* data, int bytes, int component, const char* type, int count) {
        int offset = buffer.size();
        buffer.append(static_cast<const char*>(data), bytes);
        while (buffer.size() % 4) { buffer.append('\0'); }
        int index = accessors.size();
        views.append(QJsonObject{{"buffer", 0}, {"byteOffset", offset}, {"byteLength", bytes}});
        accessors.append(QJsonObject{{"bufferView", index}, {"componentType", component},
                                    {"type", type}, {"count", count}});
        return index;
    };
    const float positions[]{ 0,0,0, 1,0,0, 0,1,0 };
    const float normals[]{ 0,0,1, 0,0,1, 0,0,1 };
    const uint16_t indices[]{ 0,1,2 };
    const uint16_t joints[]{ 0,1,0,0, 0,1,0,0, 0,1,0,0 };
    const float weights[]{ 1,0,0,0, 0,1,0,0, .5f,.5f,0,0 };
    const float binds[]{ 1,0,0,0, 0,1,0,0, 0,0,1,0, -3,0,0,1,
                         1,0,0,0, 0,1,0,0, 0,0,1,0, -5,0,0,1 };
    int p = accessor(positions, sizeof(positions), 5126, "VEC3", 3);
    int n = accessor(normals, sizeof(normals), 5126, "VEC3", 3);
    int i = accessor(indices, sizeof(indices), 5123, "SCALAR", 3);
    int j = accessor(joints, sizeof(joints), 5123, "VEC4", 3);
    int w = accessor(weights, sizeof(weights), 5126, "VEC4", 3);
    int b = accessor(binds, sizeof(binds), 5126, "MAT4", 2);
    QJsonArray nodes;
    for (int index = 0; index < 200; ++index) {
        QJsonObject node{{"name", QString("node%1").arg(index)}};
        if (index == 0) { node["mesh"] = 0; node["skin"] = 0; }
        if (index == 150) { node["translation"] = QJsonArray{3,0,0}; }
        if (index == 199) { node["translation"] = QJsonArray{5,0,0}; }
        nodes.append(node);
    }
    QJsonObject primitive{{"indices", i}, {"attributes", QJsonObject{
        {"POSITION", p}, {"NORMAL", n}, {"JOINTS_0", j}, {"WEIGHTS_0", w}}}};
    QJsonObject doc{{"asset", QJsonObject{{"version", "2.0"}}}, {"nodes", nodes},
        {"skins", QJsonArray{QJsonObject{{"joints", QJsonArray{150,199}}, {"inverseBindMatrices", b}}}},
        {"meshes", QJsonArray{QJsonObject{{"primitives", QJsonArray{primitive}}}}},
        {"buffers", QJsonArray{QJsonObject{{"byteLength", buffer.size()},
            {"uri", "data:application/octet-stream;base64," + QString::fromLatin1(buffer.toBase64())}}}},
        {"bufferViews", views}, {"accessors", accessors}};
    return QJsonDocument(doc).toJson(QJsonDocument::Compact);
}
// Every palette entry is used; unlike the large scene control, this exercises
// the supported boundary and explicit unsupported-mesh rejection at import.
inline QByteArray manyUsedJoints(int jointCount) {
    auto doc = QJsonDocument::fromJson(smallSkinInLargeScene()).object();
    const int vertices = ((jointCount + 2) / 3) * 3;
    std::vector<float> positions(vertices * 3, 0), normals(vertices * 3, 0), weights(vertices * 4, 0);
    std::vector<uint16_t> indices(vertices), joints(vertices * 4, 0);
    for (int vertex = 0; vertex < vertices; ++vertex) {
        positions[vertex * 3] = float(vertex % 3);
        positions[vertex * 3 + 1] = float(vertex / 3);
        normals[vertex * 3 + 2] = 1;
        weights[vertex * 4] = 1;
        joints[vertex * 4] = uint16_t(vertex % jointCount);
        indices[vertex] = uint16_t(vertex);
    }
    QByteArray buffer;
    QJsonArray views, accessors;
    auto accessor = [&](const auto& data, int component, const char* type, int count) {
        const int index = accessors.size(), bytes = int(data.size() * sizeof(data[0]));
        views.append(QJsonObject{{"buffer",0},{"byteOffset",buffer.size()},{"byteLength",bytes}});
        buffer.append(reinterpret_cast<const char*>(data.data()), bytes);
        while (buffer.size() % 4) { buffer.append('\0'); }
        accessors.append(QJsonObject{{"bufferView",index},{"componentType",component},{"type",type},{"count",count}});
        return index;
    };
    const int p = accessor(positions,5126,"VEC3",vertices), n = accessor(normals,5126,"VEC3",vertices);
    const int i = accessor(indices,5123,"SCALAR",vertices), j = accessor(joints,5123,"VEC4",vertices);
    const int w = accessor(weights,5126,"VEC4",vertices);
    QJsonArray skinJoints;
    for (int joint = 1; joint <= jointCount; ++joint) { skinJoints.append(joint); }
    doc["skins"] = QJsonArray{QJsonObject{{"joints",skinJoints}}};
    doc["meshes"] = QJsonArray{QJsonObject{{"primitives",QJsonArray{QJsonObject{
        {"indices",i},{"attributes",QJsonObject{{"POSITION",p},{"NORMAL",n},{"JOINTS_0",j},{"WEIGHTS_0",w}}}}}}}};
    doc["buffers"] = QJsonArray{QJsonObject{{"byteLength",buffer.size()},
        {"uri","data:application/octet-stream;base64," + QString::fromLatin1(buffer.toBase64())}}};
    doc["bufferViews"] = views; doc["accessors"] = accessors;
    return QJsonDocument(doc).toJson(QJsonDocument::Compact);
}

}
#endif
