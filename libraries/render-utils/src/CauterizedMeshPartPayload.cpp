//
//  CauterizedMeshPartPayload.cpp
//  interface/src/renderer
//
//  Created by Andrew Meadows 2017.01.17
//  Copyright 2017 High Fidelity, Inc.
//  Copyright 2024 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "CauterizedMeshPartPayload.h"

#include <PerfStat.h>
#include <graphics/ShaderConstants.h>
#include <graphics/SkinningPalette.h>

#include "CauterizedModel.h"

using namespace render;

CauterizedMeshPartPayload::CauterizedMeshPartPayload(ModelPointer model, int meshIndex, int partIndex, int shapeIndex,
                                                     const Transform& transform, const uint64_t& created)
    : ModelMeshPartPayload(model, meshIndex, partIndex, shapeIndex, transform, created) {}

void CauterizedMeshPartPayload::updateClusterBuffer(const std::vector<glm::mat4>& clusterMatrices,
                                                    const std::vector<glm::mat4>& cauterizedClusterMatrices) {
    ModelMeshPartPayload::updateClusterBuffer(clusterMatrices);

    bool valid = graphics::updateSkinningPalette(_cauterizedClusterBuffer, cauterizedClusterMatrices, _expectedClusterCount);
    if (!valid && !_reportedCauterizedPaletteError) { qWarning() << "Rejecting mismatched or oversized cauterized matrix upload"; }
    _reportedCauterizedPaletteError = !valid;
    _clusterPaletteValid = _clusterPaletteValid && valid;
}

void CauterizedMeshPartPayload::updateClusterBuffer(const std::vector<Model::TransformDualQuaternion>& clusterDualQuaternions,
                                                    const std::vector<Model::TransformDualQuaternion>& cauterizedClusterDualQuaternions) {
    ModelMeshPartPayload::updateClusterBuffer(clusterDualQuaternions);

    bool valid = graphics::updateSkinningPalette(_cauterizedClusterBuffer, cauterizedClusterDualQuaternions, _expectedClusterCount);
    if (!valid && !_reportedCauterizedPaletteError) { qWarning() << "Rejecting mismatched or oversized cauterized DQ upload"; }
    _reportedCauterizedPaletteError = !valid;
    _clusterPaletteValid = _clusterPaletteValid && valid;
}

void CauterizedMeshPartPayload::updateTransformForCauterizedMesh(const Transform& modelTransform, const Model::MeshState& meshState, bool useDualQuaternionSkinning) {
    Transform renderTransform = modelTransform;
    if (useDualQuaternionSkinning) {
        if (!hasSkinning() && !meshState.clusterDualQuaternions.empty()) {
            const auto& dq = meshState.clusterDualQuaternions[0];
            Transform transform(dq.getRotation(),
                                dq.getScale(),
                                dq.getTranslation());
            renderTransform = modelTransform.worldTransform(Transform(transform));
        }
    } else {
        if (!hasSkinning() && !meshState.clusterMatrices.empty()) {
            renderTransform = modelTransform.worldTransform(Transform(meshState.clusterMatrices[0]));
        }
    }

    _cauterizedTransform = renderTransform;
}

void CauterizedMeshPartPayload::bindTransform(gpu::Batch& batch, const Transform& transform, RenderArgs::RenderMode renderMode, size_t mirrorDepth) const {
    bool useCauterizedMesh = _enableCauterization && (renderMode != RenderArgs::RenderMode::SHADOW_RENDER_MODE && renderMode != RenderArgs::RenderMode::SECONDARY_CAMERA_RENDER_MODE) &&
        mirrorDepth == 0;
    if (useCauterizedMesh) {
        if (_cauterizedClusterBuffer) {
            batch.setUniformBuffer(graphics::slot::buffer::Skinning, _cauterizedClusterBuffer);
        }
        batch.setModelTransform(_cauterizedTransform, _previousRenderTransform);
        if (renderMode == Args::RenderMode::DEFAULT_RENDER_MODE || renderMode == Args::RenderMode::MIRROR_RENDER_MODE) {
            _previousRenderTransform = _cauterizedTransform;
        }
    } else {
        ModelMeshPartPayload::bindTransform(batch, transform, renderMode, mirrorDepth);
    }
}
