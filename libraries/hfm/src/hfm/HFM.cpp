//
//  HFM.cpp
//  libraries/hfm/src
//
//  Created by Sabrina Shanman on 2018/11/06.
//  Copyright 2018 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "HFM.h"

#include "ModelFormatLogging.h"
#include <graphics/ShaderConstants.h>
#include <cmath>

namespace {
bool finiteBind(const glm::mat4& matrix) {
    for (int column = 0; column < 4; ++column) {
        for (int row = 0; row < 4; ++row) {
            if (!std::isfinite(matrix[column][row])) { return false; }
        }
    }
    // Transform's DQ representation supports affine binds only. Validate the
    // matrix first, before inspecting a representation constructed from it.
    return std::abs(matrix[0][3]) <= 0.0001f && std::abs(matrix[1][3]) <= 0.0001f &&
        std::abs(matrix[2][3]) <= 0.0001f && std::abs(matrix[3][3] - 1.0f) <= 0.0001f;
}
bool finiteBind(const hfm::Cluster& cluster) {
    if (!finiteBind(cluster.inverseBindMatrix)) { return false; }
    glm::mat4 dqBind;
    cluster.inverseBindTransform.getMatrix(dqBind);
    return finiteBind(dqBind);
}
}

bool hfm::Mesh::validateSkinningPalette(QString& error) const {
    error.clear();
    if (!skinningDataValid) {
        error = "previously rejected skinning data";
        return false;
    }
    if (clusters.size() > GRAPHICS_MAX_SKINNING_CLUSTERS) {
        error = "palette exceeds the supported 128 clusters";
        return false;
    }
    if (clusterIndices.isEmpty() && clusterWeights.isEmpty()) { return true; }
    const qint64 expected = qint64(vertices.size()) * 4;
    if (clusterIndices.size() != expected || clusterWeights.size() != expected) {
        error = "skinning requires exactly four indices and weights per vertex";
        return false;
    }
    for (int lane = 0; lane < clusterIndices.size(); ++lane) {
        if (clusterWeights[lane] && clusterIndices[lane] >= clusters.size()) {
            error = "weighted influence is outside the actual palette";
            return false;
        }
    }
    return true;
}

bool hfm::Mesh::prepareSkinningPalette(int jointCount, QString& error) {
    error.clear();
    auto reject = [&](const QString& reason) {
        error = reason;
        skinningDataValid = false;
        clusters.clear();
        clusterIndices.clear();
        clusterWeights.clear();
        parts.clear(); // ModelCache derives render shapes from HFM parts, even for a null graphics mesh.
        _mesh.reset();
        return false;
    };
    if (!skinningDataValid) { return reject("previously rejected skinning data"); }
    if (clusterIndices.isEmpty() && clusterWeights.isEmpty()) {
        // Rigid meshes use their first cluster as a local transform.
        for (const auto& cluster : clusters) {
            if (cluster.jointIndex < 0 || cluster.jointIndex >= jointCount || !finiteBind(cluster)) {
                return reject("invalid rigid cluster joint or bind matrix");
            }
        }
        if (!validateSkinningPalette(error)) { return reject(error); }
        return true;
    }
    const qint64 expected = qint64(vertices.size()) * 4;
    if (clusterIndices.size() != expected || clusterWeights.size() != expected) {
        return reject("skinning requires exactly four indices and weights per vertex");
    }
    QVector<int> remap(clusters.size(), -1);
    for (int lane = 0; lane < clusterIndices.size(); ++lane) {
        if (!clusterWeights[lane]) { continue; }
        int index = clusterIndices[lane];
        if (index >= clusters.size()) { return reject("weighted influence is outside the actual palette"); }
        remap[index] = 0;
    }
    QVector<hfm::Cluster> used;
    for (int index = 0; index < clusters.size(); ++index) {
        if (remap[index] < 0) { continue; }
        const auto& cluster = clusters[index];
        if (cluster.jointIndex < 0 || cluster.jointIndex >= jointCount || !finiteBind(cluster)) {
            return reject("invalid used cluster joint or bind matrix");
        }
        if (used.size() == GRAPHICS_MAX_SKINNING_CLUSTERS) {
            return reject("used skinning palette exceeds the supported 128 clusters; mesh rejected");
        }
        remap[index] = used.size();
        used.append(cluster); // Preserve the joint index and BOTH inverse bind representations.
    }
    for (int lane = 0; lane < clusterIndices.size(); ++lane) {
        clusterIndices[lane] = clusterWeights[lane] ? uint16_t(remap[clusterIndices[lane]]) : 0;
    }
    clusters = used;
    return true;
}

void HFMMaterial::getTextureNames(QSet<QString>& textureList) const {
    if (!normalTexture.isNull()) {
        textureList.insert(normalTexture.name);
    }
    if (!albedoTexture.isNull()) {
        textureList.insert(albedoTexture.name);
    }
    if (!opacityTexture.isNull()) {
        textureList.insert(opacityTexture.name);
    }
    if (!glossTexture.isNull()) {
        textureList.insert(glossTexture.name);
    }
    if (!roughnessTexture.isNull()) {
        textureList.insert(roughnessTexture.name);
    }
    if (!specularTexture.isNull()) {
        textureList.insert(specularTexture.name);
    }
    if (!metallicTexture.isNull()) {
        textureList.insert(metallicTexture.name);
    }
    if (!emissiveTexture.isNull()) {
        textureList.insert(emissiveTexture.name);
    }
    if (!occlusionTexture.isNull()) {
        textureList.insert(occlusionTexture.name);
    }
    if (!scatteringTexture.isNull()) {
        textureList.insert(scatteringTexture.name);
    }
    if (!lightmapTexture.isNull()) {
        textureList.insert(lightmapTexture.name);
    }

    if (isMToonMaterial) {
        if (!shadeTexture.isNull()) {
            textureList.insert(shadeTexture.name);
        }
        if (!shadingShiftTexture.isNull()) {
            textureList.insert(shadingShiftTexture.name);
        }
        if (!matcapTexture.isNull()) {
            textureList.insert(matcapTexture.name);
        }
        if (!rimTexture.isNull()) {
            textureList.insert(rimTexture.name);
        }
        if (!uvAnimationTexture.isNull()) {
            textureList.insert(uvAnimationTexture.name);
        }
    }
}

void HFMMaterial::setMaxNumPixelsPerTexture(int maxNumPixels) {
    normalTexture.maxNumPixels = maxNumPixels;
    albedoTexture.maxNumPixels = maxNumPixels;
    opacityTexture.maxNumPixels = maxNumPixels;
    glossTexture.maxNumPixels = maxNumPixels;
    roughnessTexture.maxNumPixels = maxNumPixels;
    specularTexture.maxNumPixels = maxNumPixels;
    metallicTexture.maxNumPixels = maxNumPixels;
    emissiveTexture.maxNumPixels = maxNumPixels;
    occlusionTexture.maxNumPixels = maxNumPixels;
    scatteringTexture.maxNumPixels = maxNumPixels;
    lightmapTexture.maxNumPixels = maxNumPixels;

    shadeTexture.maxNumPixels = maxNumPixels;
    shadingShiftTexture.maxNumPixels = maxNumPixels;
    matcapTexture.maxNumPixels = maxNumPixels;
    rimTexture.maxNumPixels = maxNumPixels;
    uvAnimationTexture.maxNumPixels = maxNumPixels;
}

bool HFMMaterial::needTangentSpace() const {
    return !normalTexture.isNull();
}

QStringList HFMModel::getJointNames() const {
    QStringList names;
    foreach (const HFMJoint& joint, joints) {
        names.append(joint.name);
    }
    return names;
}

bool HFMModel::hasBlendedMeshes() const {
    if (!meshes.isEmpty()) {
        foreach (const HFMMesh& mesh, meshes) {
            if (!mesh.blendshapes.isEmpty()) {
                return true;
            }
        }
    }
    return false;
}

Extents HFMModel::getUnscaledMeshExtents() const {
    // even though our caller asked for "unscaled" we need to include any fst scaling, translation, and rotation, which
    // is captured in the offset matrix
    glm::vec3 minimum = glm::vec3(offset * glm::vec4(meshExtents.minimum, 1.0f));
    glm::vec3 maximum = glm::vec3(offset * glm::vec4(meshExtents.maximum, 1.0f));
    Extents scaledExtents = { minimum, maximum };
    return scaledExtents;
}

// TODO: Move to graphics::Mesh when Sam's ready
bool HFMModel::convexHullContains(const glm::vec3& point) const {
    if (!meshExtents.containsPoint(point)) {
        return false;
    }

    auto checkEachPrimitive = [=, this](HFMMesh& mesh, QVector<int> indices, int primitiveSize) -> bool {
        // Check whether the point is "behind" all the primitives.
        // But first must transform from model-frame into mesh-frame
        glm::vec3 transformedPoint = glm::vec3(glm::inverse(offset * mesh.modelTransform) * glm::vec4(point, 1.0f));
        int verticesSize = mesh.vertices.size();
        for (int j = 0;
            j < indices.size() - 2; // -2 in case the vertices aren't the right size -- we access j + 2 below
            j += primitiveSize) {
            if (indices[j] < verticesSize &&
                indices[j + 1] < verticesSize &&
                indices[j + 2] < verticesSize &&
                !isPointBehindTrianglesPlane(transformedPoint,
                    mesh.vertices[indices[j]],
                    mesh.vertices[indices[j + 1]],
                    mesh.vertices[indices[j + 2]])) {
                // it's not behind at least one so we bail
                return false;
            }
        }
        return true;
    };

    // Check that the point is contained in at least one convex mesh.
    for (auto mesh : meshes) {
        bool insideMesh = true;

        // To be considered inside a convex mesh,
        // the point needs to be "behind" all the primitives respective planes.
        for (auto part : mesh.parts) {
            // run through all the triangles and quads
            if (!checkEachPrimitive(mesh, part.triangleIndices, 3) ||
                !checkEachPrimitive(mesh, part.quadIndices, 4)) {
                // If not, the point is outside, bail for this mesh
                insideMesh = false;
                continue;
            }
        }
        if (insideMesh) {
            // It's inside this mesh, return true.
            return true;
        }
    }

    // It wasn't in any mesh, return false.
    return false;
}

QString HFMModel::getModelNameOfMesh(int meshIndex) const {
    if (meshIndicesToModelNames.contains(meshIndex)) {
        return meshIndicesToModelNames.value(meshIndex);
    }
    return QString();
}

void HFMModel::computeKdops() {
    const float INV_SQRT_3 = 0.57735026918f;
    ShapeVertices cardinalDirections = {
        Vectors::UNIT_X,
        Vectors::UNIT_Y,
        Vectors::UNIT_Z,
        glm::vec3(INV_SQRT_3,  INV_SQRT_3,  INV_SQRT_3),
        glm::vec3(INV_SQRT_3, -INV_SQRT_3,  INV_SQRT_3),
        glm::vec3(INV_SQRT_3,  INV_SQRT_3, -INV_SQRT_3),
        glm::vec3(INV_SQRT_3, -INV_SQRT_3, -INV_SQRT_3)
    };
    if (joints.size() != (int)shapeVertices.size()) {
        return;
    }
    // now that all joints have been scanned compute a k-Dop bounding volume of mesh
    for (int i = 0; i < joints.size(); ++i) {
        HFMJoint& joint = joints[i];

        // NOTE: points are in joint-frame
        ShapeVertices& points = shapeVertices.at(i);
        glm::quat rotOffset = jointRotationOffsets.contains(i) ? glm::inverse(jointRotationOffsets[i]) : quat();
        if (points.size() > 0) {
            // compute average point
            glm::vec3 avgPoint = glm::vec3(0.0f);
            for (uint32_t j = 0; j < points.size(); ++j) {
                points[j] = rotOffset * points[j];
                avgPoint += points[j];
            }
            avgPoint /= (float)points.size();
            joint.shapeInfo.avgPoint = avgPoint;

            // compute a k-Dop bounding volume
            for (uint32_t j = 0; j < cardinalDirections.size(); ++j) {
                float maxDot = -FLT_MAX;
                float minDot = FLT_MIN;
                for (uint32_t k = 0; k < points.size(); ++k) {
                    float kDot = glm::dot(cardinalDirections[j], points[k] - avgPoint);
                    if (kDot > maxDot) {
                        maxDot = kDot;
                    }
                    if (kDot < minDot) {
                        minDot = kDot;
                    }
                }
                joint.shapeInfo.points.push_back(avgPoint + maxDot * cardinalDirections[j]);
                joint.shapeInfo.dots.push_back(maxDot);
                joint.shapeInfo.points.push_back(avgPoint + minDot * cardinalDirections[j]);
                joint.shapeInfo.dots.push_back(-minDot);
            }
            generateBoundryLinesForDop14(joint.shapeInfo.dots, joint.shapeInfo.avgPoint, joint.shapeInfo.debugLines);
        }
    }
}

void HFMModel::debugDump() {
    qCDebug(modelformat) << "---------------- hfmModel ----------------";
    qCDebug(modelformat) << "  originalURL =" << originalURL;

    qCDebug(modelformat) << "  hasSkeletonJoints =" << hasSkeletonJoints;
    qCDebug(modelformat) << "  offset =" << offset;

    qCDebug(modelformat) << "  neckPivot = " << neckPivot;

    qCDebug(modelformat) << "  bindExtents.size() = " << bindExtents.size();
    qCDebug(modelformat) << "  meshExtents.size() = " << meshExtents.size();

    qCDebug(modelformat) << "  jointIndices.size() =" << jointIndices.size();
    qCDebug(modelformat) << "  joints.count() =" << joints.count();

    qCDebug(modelformat) << "---------------- Meshes ----------------";
    qCDebug(modelformat) << "  meshes.count() =" << meshes.count();
    qCDebug(modelformat) << "  blendshapeChannelNames = " << blendshapeChannelNames;
    foreach(HFMMesh mesh, meshes) {
        qCDebug(modelformat) << "    meshpointer =" << mesh._mesh.get();
        qCDebug(modelformat) << "    meshindex =" << mesh.meshIndex;
        qCDebug(modelformat) << "    vertices.count() =" << mesh.vertices.size();
        qCDebug(modelformat) << "    colors.count() =" << mesh.colors.count();
        qCDebug(modelformat) << "    normals.count() =" << mesh.normals.size();
        qCDebug(modelformat) << "    tangents.count() =" << mesh.tangents.size();
        qCDebug(modelformat) << "    colors.count() =" << mesh.colors.count();
        qCDebug(modelformat) << "    texCoords.count() =" << mesh.texCoords.count();
        qCDebug(modelformat) << "    texCoords1.count() =" << mesh.texCoords1.count();
        qCDebug(modelformat) << "    clusterIndices.count() =" << mesh.clusterIndices.count();
        qCDebug(modelformat) << "    clusterWeights.count() =" << mesh.clusterWeights.count();
        qCDebug(modelformat) << "    modelTransform =" << mesh.modelTransform;
        qCDebug(modelformat) << "    parts.count() =" << mesh.parts.count();

        qCDebug(modelformat) << "---------------- Meshes (blendshapes)--------";
        foreach(HFMBlendshape bshape, mesh.blendshapes) {
            qCDebug(modelformat) << "    bshape.indices.count() =" << bshape.indices.count();
            qCDebug(modelformat) << "    bshape.vertices.count() =" << bshape.vertices.count();
            qCDebug(modelformat) << "    bshape.normals.count() =" << bshape.normals.count();
        }

        qCDebug(modelformat) << "---------------- Meshes (meshparts)--------";
        foreach(HFMMeshPart meshPart, mesh.parts) {
            qCDebug(modelformat) << "        quadIndices.count() =" << meshPart.quadIndices.count();
            qCDebug(modelformat) << "        triangleIndices.count() =" << meshPart.triangleIndices.count();
            qCDebug(modelformat) << "        materialID =" << meshPart.materialID;
        }

        qCDebug(modelformat) << "---------------- Meshes (clusters)--------";
        qCDebug(modelformat) << "    clusters.count() =" << mesh.clusters.count();
        foreach(HFMCluster cluster, mesh.clusters) {
            qCDebug(modelformat) << "        jointIndex =" << cluster.jointIndex;
            qCDebug(modelformat) << "        inverseBindMatrix =" << cluster.inverseBindMatrix;
        }
    }

    qCDebug(modelformat) << "---------------- AnimationFrames ----------------";
    foreach(HFMAnimationFrame anim, animationFrames) {
        qCDebug(modelformat) << "  anim.translations = " << anim.translations;
        qCDebug(modelformat) << "  anim.rotations = " << anim.rotations;
    }

    qCDebug(modelformat) << "---------------- Mesh model names ----------------";
    QList<int> mitomona_keys = meshIndicesToModelNames.keys();
    foreach(int key, mitomona_keys) {
        qCDebug(modelformat) << "    meshIndicesToModelNames key =" << key << "  val =" << meshIndicesToModelNames[key];
    }

    qCDebug(modelformat) << "---------------- Materials ----------------";
    foreach(HFMMaterial mat, materials) {
        qCDebug(modelformat) << "  mat.materialID =" << mat.materialID;
        qCDebug(modelformat) << "  diffuseColor =" << mat.diffuseColor;
        qCDebug(modelformat) << "  diffuseFactor =" << mat.diffuseFactor;
        qCDebug(modelformat) << "  specularColor =" << mat.specularColor;
        qCDebug(modelformat) << "  specularFactor =" << mat.specularFactor;
        qCDebug(modelformat) << "  emissiveColor =" << mat.emissiveColor;
        qCDebug(modelformat) << "  emissiveFactor =" << mat.emissiveFactor;
        qCDebug(modelformat) << "  shininess =" << mat.shininess;
        qCDebug(modelformat) << "  opacity =" << mat.opacity;
        qCDebug(modelformat) << "  metallic =" << mat.metallic;
        qCDebug(modelformat) << "  roughness =" << mat.roughness;
        qCDebug(modelformat) << "  emissiveIntensity =" << mat.emissiveIntensity;
        qCDebug(modelformat) << "  ambientFactor =" << mat.ambientFactor;

        qCDebug(modelformat) << "  materialID =" << mat.materialID;
        qCDebug(modelformat) << "  name =" << mat.name;
        qCDebug(modelformat) << "  shadingModel =" << mat.shadingModel;
        qCDebug(modelformat) << "  _material =" << mat._material.get();

        qCDebug(modelformat) << "  normalTexture =" << mat.normalTexture.filename;
        qCDebug(modelformat) << "  albedoTexture =" << mat.albedoTexture.filename;
        qCDebug(modelformat) << "  opacityTexture =" << mat.opacityTexture.filename;

        qCDebug(modelformat) << "  lightmapParams =" << mat.lightmapParams;

        qCDebug(modelformat) << "  isPBSMaterial =" << mat.isPBSMaterial;
        qCDebug(modelformat) << "  useNormalMap =" << mat.useNormalMap;
        qCDebug(modelformat) << "  useAlbedoMap =" << mat.useAlbedoMap;
        qCDebug(modelformat) << "  useOpacityMap =" << mat.useOpacityMap;
        qCDebug(modelformat) << "  useRoughnessMap =" << mat.useRoughnessMap;
        qCDebug(modelformat) << "  useSpecularMap =" << mat.useSpecularMap;
        qCDebug(modelformat) << "  useMetallicMap =" << mat.useMetallicMap;
        qCDebug(modelformat) << "  useEmissiveMap =" << mat.useEmissiveMap;
        qCDebug(modelformat) << "  useOcclusionMap =" << mat.useOcclusionMap;

        qCDebug(modelformat) << "  isMToonMaterial =" << mat.isMToonMaterial;
        qCDebug(modelformat) << "  shadeTexture =" << mat.shadeTexture.filename;
        qCDebug(modelformat) << "  shadingShiftTexture =" << mat.shadingShiftTexture.filename;
        qCDebug(modelformat) << "  matcapTexture =" << mat.matcapTexture.filename;
        qCDebug(modelformat) << "  rimTexture =" << mat.rimTexture.filename;
        qCDebug(modelformat) << "  uvAnimationTexture =" << mat.uvAnimationTexture.filename;
    }

    qCDebug(modelformat) << "---------------- Joints ----------------";
    foreach(HFMJoint joint, joints) {
        qCDebug(modelformat) << "    shapeInfo.avgPoint =" << joint.shapeInfo.avgPoint;
        qCDebug(modelformat) << "    shapeInfo.debugLines =" << joint.shapeInfo.debugLines;
        qCDebug(modelformat) << "    shapeInfo.dots =" << joint.shapeInfo.dots;
        qCDebug(modelformat) << "    shapeInfo.points =" << joint.shapeInfo.points;

        qCDebug(modelformat) << "    parentIndex" << joint.parentIndex;
        qCDebug(modelformat) << "    distanceToParent" << joint.distanceToParent;
        qCDebug(modelformat) << "    translation" << joint.translation;
        qCDebug(modelformat) << "    preTransform" << joint.preTransform;
        qCDebug(modelformat) << "    preRotation" << joint.preRotation;
        qCDebug(modelformat) << "    rotation" << joint.rotation;
        qCDebug(modelformat) << "    postRotation" << joint.postRotation;
        qCDebug(modelformat) << "    postTransform" << joint.postTransform;
        qCDebug(modelformat) << "    transform" << joint.transform;
        qCDebug(modelformat) << "    rotationMin" << joint.rotationMin;
        qCDebug(modelformat) << "    rotationMax" << joint.rotationMax;
        qCDebug(modelformat) << "    inverseDefaultRotation" << joint.inverseDefaultRotation;
        qCDebug(modelformat) << "    inverseBindRotation" << joint.inverseBindRotation;
        qCDebug(modelformat) << "    bindTransform" << joint.bindTransform;
        qCDebug(modelformat) << "    name" << joint.name;
        qCDebug(modelformat) << "    isSkeletonJoint" << joint.isSkeletonJoint;
        qCDebug(modelformat) << "    bindTransformFoundInCluster" << joint.hasGeometricOffset;
        qCDebug(modelformat) << "    bindTransformFoundInCluster" << joint.geometricTranslation;
        qCDebug(modelformat) << "    bindTransformFoundInCluster" << joint.geometricRotation;
        qCDebug(modelformat) << "    bindTransformFoundInCluster" << joint.geometricScaling;
    }
}
