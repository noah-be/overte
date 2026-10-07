// SPDX-License-Identifier: Apache-2.0
// Read-only CPU audit of the installed native FBX serializer; no GPU or network.
#include <QCoreApplication>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <FBXSerializer.h>
#include <cstdio>

QJsonArray vector(const glm::vec3& value) {
    return { value.x, value.y, value.z };
}

QString textureBasename(const HFMTexture& texture) {
    QString name = QString::fromUtf8(texture.filename);
    name.replace('\\', '/');
    return QFileInfo(name).fileName();
}

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    if (argc != 2) {
        return 2;
    }
    QFile source(QString::fromLocal8Bit(argv[1]));
    if (!source.open(QIODevice::ReadOnly) || source.size() > 32 * 1024 * 1024) {
        return 3;
    }
    try {
        FBXSerializer reader;
        auto model = reader.read(source.readAll(), {}, QUrl("https://invalid.example/offline.fbx"));
        if (!model) {
            return 4;
        }
        QJsonArray materials;
        for (const auto& material : model->materials) {
            QJsonObject item {
                { "name", material.name },
                { "pbs", material.isPBSMaterial },
                { "useAlbedoMapDebug", material.useAlbedoMap },
                { "useRoughnessMapDebug", material.useRoughnessMap },
                { "diffuse", vector(material.diffuseColor) },
                { "diffuseFactor", material.diffuseFactor },
                { "opacity", material.opacity },
                { "metallic", material.metallic },
                { "roughness", material.roughness },
                { "albedoTexture", textureBasename(material.albedoTexture) },
                { "opacityTexture", textureBasename(material.opacityTexture) },
                { "roughnessTexture", textureBasename(material.roughnessTexture) },
                { "metallicTexture", textureBasename(material.metallicTexture) }
            };
            if (material._material) {
                item["effectiveAlbedoSRGB"] = vector(material._material->getAlbedo());
                item["effectiveOpacity"] = material._material->getOpacity();
                item["effectiveRoughness"] = material._material->getRoughness();
                item["effectiveMetallic"] = material._material->getMetallic();
            }
            materials.append(item);
        }
        auto json = QJsonDocument(QJsonObject {
            { "qtVersion", qVersion() },
            { "glmVersion", GLM_VERSION },
            { "meshes", model->meshes.size() },
            { "materials", materials }
        }).toJson();
        return fwrite(json.constData(), 1, json.size(), stdout) == size_t(json.size()) ? 0 : 5;
    } catch (const QString& error) {
        // stderr stays in the operator's private output directory.
        fprintf(stderr, "Native FBX parser rejected offline input: %s\n", qPrintable(error));
        return 4;
    }
}
