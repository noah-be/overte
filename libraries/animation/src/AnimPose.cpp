//
//  AnimPose.cpp
//
//  Created by Anthony J. Thibault on 10/14/15.
//  Copyright (c) 2015 High Fidelity, Inc. All rights reserved.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "AnimPose.h"
#include <GLMHelpers.h>
#include <algorithm>
#include <cmath>
#include "AnimUtil.h"

const AnimPose AnimPose::identity = AnimPose(glm::vec3(1.0f),
                                             glm::quat(),
                                             glm::vec3(0.0f));

AnimPose::AnimPose(const glm::mat4& mat) {
    glm::mat3 m(mat);
    _scale = glm::vec3(glm::length(m[0]), glm::length(m[1]), glm::length(m[2]));
    _trans = extractTranslation(mat);
    float det = glm::determinant(m);

    auto finiteVec3 = [](const glm::vec3& value) {
        return std::isfinite(value.x) && std::isfinite(value.y) && std::isfinite(value.z);
    };
    if (!finiteVec3(_scale) || !finiteVec3(_trans) || !std::isfinite(det)) {
        _scale = glm::vec3(1.0f);
        _rot = glm::quat(1.0f, 0.0f, 0.0f, 0.0f);
        _trans = glm::vec3(0.0f);
        return;
    }

    glm::mat3 tmp;
    if (det < 0.0f) {
        _scale *= -1.0f;
    }

    // quat_cast doesn't work so well with scaled matrices, so cancel out scale.
    // also, as a side effect, multiply mirrored matrices by -1 to get the right rotation out.
    bool validAxis[3];
    int validAxisCount { 0 };
    for (int i = 0; i < 3; ++i) {
        validAxis[i] = glm::abs(_scale[i]) > EPSILON;
        validAxisCount += validAxis[i] ? 1 : 0;
        tmp[i] = validAxis[i] ? m[i] * (1.0f / _scale[i]) : glm::vec3(0.0f);
    }
    if (validAxisCount < 2) {
        // One axis is not enough to recover a unique orientation.
        _rot = glm::quat(1.0f, 0.0f, 0.0f, 0.0f);
        return;
    } else if (validAxisCount == 2) {
        glm::vec3 reconstructedAxis;
        int missingAxis;
        if (!validAxis[0]) {
            missingAxis = 0;
            reconstructedAxis = glm::cross(tmp[1], tmp[2]);
        } else if (!validAxis[1]) {
            missingAxis = 1;
            reconstructedAxis = glm::cross(tmp[2], tmp[0]);
        } else {
            missingAxis = 2;
            reconstructedAxis = glm::cross(tmp[0], tmp[1]);
        }
        float reconstructedLength = glm::length(reconstructedAxis);
        if (!std::isfinite(reconstructedLength) || reconstructedLength <= EPSILON) {
            _rot = glm::quat(1.0f, 0.0f, 0.0f, 0.0f);
            return;
        }
        tmp[missingAxis] = reconstructedAxis / reconstructedLength;
    }
    _rot = glm::quat_cast(tmp);

    // normalize quat if necessary
    float lengthSquared = glm::length2(_rot);
    if (!std::isfinite(lengthSquared) || lengthSquared <= EPSILON) {
        _rot = glm::quat(1.0f, 0.0f, 0.0f, 0.0f);
    } else if (glm::abs(lengthSquared - 1.0f) > EPSILON) {
        float oneOverLength = 1.0f / sqrtf(lengthSquared);
        _rot = glm::quat(_rot.w * oneOverLength, _rot.x * oneOverLength, _rot.y * oneOverLength, _rot.z * oneOverLength);
    }
}

glm::vec3 AnimPose::operator*(const glm::vec3& rhs) const {
    return _trans + (_rot * (_scale * rhs));
}

glm::vec3 AnimPose::xformPoint(const glm::vec3& rhs) const {
    return *this * rhs;
}

// really slow, but accurate for transforms with non-uniform scale
glm::vec3 AnimPose::xformVector(const glm::vec3& rhs) const {
    glm::vec3 xAxis = _rot * glm::vec3(_scale.x, 0.0f, 0.0f);
    glm::vec3 yAxis = _rot * glm::vec3(0.0f, _scale.y, 0.0f);
    glm::vec3 zAxis = _rot * glm::vec3(0.0f, 0.0f, _scale.z);
    glm::mat3 mat(xAxis, yAxis, zAxis);
    glm::mat3 transInvMat = glm::inverse(glm::transpose(mat));
    return transInvMat * rhs;
}

// faster, but does not handle non-uniform scale correctly.
glm::vec3 AnimPose::xformVectorFast(const glm::vec3& rhs) const {
    return _rot * (_scale * rhs);
}

AnimPose AnimPose::operator*(const AnimPose& rhs) const {
    glm::mat4 result;
    glm_mat4u_mul(*this, rhs, result);
    return AnimPose(result);
}

AnimPose AnimPose::inverse() const {
    return AnimPose(glm::inverse(static_cast<glm::mat4>(*this)));
}

// mirror about x-axis without applying negative scale.
AnimPose AnimPose::mirror() const {
    return AnimPose(_scale, glm::quat(_rot.w, _rot.x, -_rot.y, -_rot.z), glm::vec3(-_trans.x, _trans.y, _trans.z));
}

AnimPose::operator glm::mat4() const {
    glm::vec3 xAxis = _rot * glm::vec3(_scale.x, 0.0f, 0.0f);
    glm::vec3 yAxis = _rot * glm::vec3(0.0f, _scale.y, 0.0f);
    glm::vec3 zAxis = _rot * glm::vec3(0.0f, 0.0f, _scale.z);
    return glm::mat4(glm::vec4(xAxis, 0.0f), glm::vec4(yAxis, 0.0f),
        glm::vec4(zAxis, 0.0f), glm::vec4(_trans, 1.0f));
}

void AnimPose::blend(const AnimPose& srcPose, float alpha) {
    _scale = lerp(srcPose._scale, _scale, alpha);
    _rot = safeLerp(srcPose._rot, _rot, alpha);
    _trans = lerp(srcPose._trans, _trans, alpha);
}
