//
//  AnimationCache.cpp
//  libraries/animation/src/
//
//  Created by Andrzej Kapolka on 4/14/14.
//  Copyright (c) 2014 High Fidelity, Inc. All rights reserved.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "AnimationCache.h"

#include <QRunnable>
#include <QThreadPool>
#include <QElapsedTimer>
#include <QCryptographicHash>
#include <Finally.h>
#include <PhoneLoadingDiagnostics.h>

#include <shared/QtHelpers.h>
#include <Trace.h>
#include <StatTracker.h>
#include <Profile.h>

#include "AnimationLogging.h"
#include <FBXSerializer.h>

#if defined(ANDROID_APP_PHONE_INTERFACE)
// Diagnostic equivalence check of the data consumed by animation retargeting.
static QByteArray animationPoseDigest(const HFMModel& model) {
    static_assert(sizeof(glm::quat) == 4 * sizeof(float), "packed quaternion required");
    static_assert(sizeof(glm::vec3) == 3 * sizeof(float), "packed vector required");
    QCryptographicHash digest(QCryptographicHash::Sha256);
    auto bytes = [&](const auto& value) { digest.addData(reinterpret_cast<const char*>(&value), sizeof(value)); };
    bytes(model.offset);
    for (const auto& joint : model.joints) {
        auto name = joint.name.toUtf8();
        const int length = name.size(); bytes(length); digest.addData(name);
        bytes(joint.parentIndex); bytes(joint.translation); bytes(joint.preTransform);
        bytes(joint.preRotation); bytes(joint.rotation); bytes(joint.postRotation); bytes(joint.postTransform);
        bytes(joint.transform); bytes(joint.rotationMin); bytes(joint.rotationMax);
        bytes(joint.inverseDefaultRotation); bytes(joint.inverseBindRotation); bytes(joint.distanceToParent);
        bytes(joint.isSkeletonJoint); bytes(joint.bindTransformFoundInCluster);
        if (joint.bindTransformFoundInCluster) { bytes(joint.bindTransform); }
        bytes(joint.hasGeometricOffset);
        if (joint.hasGeometricOffset) {
            bytes(joint.geometricTranslation); bytes(joint.geometricRotation); bytes(joint.geometricScaling);
        }
    }
    for (auto it = model.jointRotationOffsets.constBegin(); it != model.jointRotationOffsets.constEnd(); ++it) {
        const int index = it.key(); bytes(index); bytes(it.value());
    }
    for (const auto& mesh : model.meshes) {
        for (const auto& cluster : mesh.clusters) { bytes(cluster.jointIndex); bytes(cluster.inverseBindMatrix); }
    }
    for (const auto& frame : model.animationFrames) {
        const int rotations = frame.rotations.size(), translations = frame.translations.size();
        bytes(rotations); bytes(translations);
        digest.addData(reinterpret_cast<const char*>(frame.rotations.constData()), rotations * sizeof(glm::quat));
        digest.addData(reinterpret_cast<const char*>(frame.translations.constData()), translations * sizeof(glm::vec3));
    }
    return digest.result().toHex();
}
#endif

int animationPointerMetaTypeId = qRegisterMetaType<AnimationPointer>();

AnimationCache::AnimationCache(QObject* parent) :
    ResourceCache(parent)
{
#if defined(Q_OS_ANDROID)
    const qint64 ANIMATION_DEFAULT_UNUSED_MAX_SIZE = 8 * BYTES_PER_MEGABYTES;
#else
    const qint64 ANIMATION_DEFAULT_UNUSED_MAX_SIZE = 50 * BYTES_PER_MEGABYTES;
#endif
    setUnusedResourceCacheSize(ANIMATION_DEFAULT_UNUSED_MAX_SIZE);
    setObjectName("AnimationCache");
}

AnimationPointer AnimationCache::getAnimation(const QUrl& url) {
    return getResource(url).staticCast<Animation>();
}

QSharedPointer<Resource> AnimationCache::createResource(const QUrl& url) {
    return QSharedPointer<Animation>(new Animation(url), &Resource::deleter);
}

QSharedPointer<Resource> AnimationCache::createResourceCopy(const QSharedPointer<Resource>& resource) {
    return QSharedPointer<Animation>(new Animation(*resource.staticCast<Animation>()), &Resource::deleter);
}

AnimationReader::AnimationReader(const QUrl& url, const QByteArray& data) :
    _url(url),
    _data(data) {
    DependencyManager::get<StatTracker>()->incrementStat("PendingProcessing");
}

void AnimationReader::run() {
    QElapsedTimer loadingTimer; loadingTimer.start();
    const auto loadingHash = QCryptographicHash::hash(_url.toEncoded(), QCryptographicHash::Md5).toHex();
    PHONE_LOADING("phase=animation_start url_hash=%s bytes=%d", loadingHash.constData(), _data.size());
    Finally loadingRecord([&] {
        PHONE_LOADING("phase=animation_end url_hash=%s ms=%lld", loadingHash.constData(), (long long)loadingTimer.elapsed());
    });
    DependencyManager::get<StatTracker>()->decrementStat("PendingProcessing");
    CounterStat counter("Processing");

    PROFILE_RANGE_EX(resource_parse, __FUNCTION__, 0xFF00FF00, 0, { { "url", _url.toString() } });
    auto originalPriority = QThread::currentThread()->priority();
    if (originalPriority == QThread::InheritPriority) {
        originalPriority = QThread::NormalPriority;
    }
    QThread::currentThread()->setPriority(QThread::LowPriority);
    try {
        if (_data.isEmpty()) {
            throw QString("Reply is NULL ?!");
        }
        QString urlname = _url.path().toLower();
        bool urlValid = true;
        urlValid &= !urlname.isEmpty();
        urlValid &= !_url.path().isEmpty();

        if (urlValid) {
            // Parse the FBX directly from the QNetworkReply
            HFMModel::Pointer hfmModel;
            if (_url.path().toLower().endsWith(".fbx")) {
                QVariantHash animationMapping;
#if defined(ANDROID_APP_PHONE_INTERFACE)
                // Keep the unaccepted parser experiment opt-in, including
                // when diagnostics are disabled or Android properties reset.
                bool skipUnusedCurveData = false;
                if (phoneLoadingDiagnosticsEnabled() && _url.scheme() == "qrc") {
                    char value[PROP_VALUE_MAX] {};
                    skipUnusedCurveData =
                        __system_property_get("debug.overte.loading.animation_full", value) == 1 && value[0] == '0';
                }
                animationMapping.insert("_phoneSkipUnusedAnimationCurveData", skipUnusedCurveData);
#endif
                hfmModel = FBXSerializer().read(_data, animationMapping, _url.path());
#if defined(ANDROID_APP_PHONE_INTERFACE)
                if (phoneLoadingDiagnosticsEnabled() && hfmModel) {
                    PHONE_LOADING("phase=animation_digest url_hash=%s sha256=%s", loadingHash.constData(), animationPoseDigest(*hfmModel).constData());
                }
#endif
                PHONE_LOADING("phase=animation_parsed url_hash=%s frames=%d joints=%d ok=%d", loadingHash.constData(),
                    hfmModel ? hfmModel->animationFrames.size() : 0, hfmModel ? hfmModel->joints.size() : 0, hfmModel ? 1 : 0);
            } else {
                QString errorStr("usupported format");
                emit onError(299, errorStr);
            }
            emit onSuccess(hfmModel);
        } else {
            throw QString("url is invalid");
        }

    } catch (const QString& error) {
        emit onError(299, error);
    }
    QThread::currentThread()->setPriority(originalPriority);
}

bool Animation::isLoaded() const {
    return _loaded && _hfmModel;
}

QStringList Animation::getJointNames() const {
    if (QThread::currentThread() != thread()) {
        QStringList result;
        BLOCKING_INVOKE_METHOD(const_cast<Animation*>(this), "getJointNames",
            Q_RETURN_ARG(QStringList, result));
        return result;
    }
    QStringList names;
    if (_hfmModel) {
        foreach (const HFMJoint& joint, _hfmModel->joints) {
            names.append(joint.name);
        }
    }
    return names;
}

QVector<HFMAnimationFrame> Animation::getFrames() const {
    if (QThread::currentThread() != thread()) {
        QVector<HFMAnimationFrame> result;
        BLOCKING_INVOKE_METHOD(const_cast<Animation*>(this), "getFrames",
            Q_RETURN_ARG(QVector<HFMAnimationFrame>, result));
        return result;
    }
    if (_hfmModel) {
        return _hfmModel->animationFrames;
    } else {
        return QVector<HFMAnimationFrame>();
    }
}

const QVector<HFMAnimationFrame>& Animation::getFramesReference() const {
    return _hfmModel->animationFrames;
}

void Animation::downloadFinished(const QByteArray& data) {
    PHONE_LOADING("phase=animation_queue url_hash=%s bytes=%d", QCryptographicHash::hash(_url.toEncoded(), QCryptographicHash::Md5).toHex().constData(), data.size());
    // parse the animation/fbx file on a background thread.
    AnimationReader* animationReader = new AnimationReader(_url, data);
    connect(animationReader, SIGNAL(onSuccess(HFMModel::Pointer)), SLOT(animationParseSuccess(HFMModel::Pointer)));
    connect(animationReader, SIGNAL(onError(int, QString)), SLOT(animationParseError(int, QString)));
    QThreadPool::globalInstance()->start(animationReader);
}

void Animation::animationParseSuccess(HFMModel::Pointer hfmModel) {
    _hfmModel = hfmModel;
    finishedLoading(true);
}

void Animation::animationParseError(int error, QString str) {
    qCCritical(animation) << "Animation parse error, code =" << error << str;
    emit failed(QNetworkReply::UnknownContentError);
    finishedLoading(false);
}
