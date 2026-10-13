// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
// Real local bytes behind an explicit ResourceManager provider boundary; no live server or renderer.
#pragma once
#include <QCoreApplication>
#include <QBuffer>
#include <QEventLoop>
#include <QFile>
#include <QDir>
#include <QTimer>
#include <QImage>
#include <QLoggingCategory>
#include <shared/HifiTypes.h>
#include <glm/glm.hpp>
#include <sstream>
#include <iterator>
#include <cassert>
#include <tuple>
#include <memory>
#include <QFileInfo>
#include <QTemporaryDir>
Q_DECLARE_LOGGING_CATEGORY(modelformat)
struct ResourceRequest : QObject {
    Q_OBJECT
public:
    enum Result { Success, Error };
    QString file;
    QByteArray bytes;
    Result result {Error};
    void send(){QTimer::singleShot(0,this,[this]{QFile source(file);if(source.open(QFile::ReadOnly)){bytes=source.readAll();result=Success;}emit finished();});}
    Result getResult(){return result;}
    QByteArray getData(){return bytes;}
signals: void finished();
};
struct ResourceManager : QObject {
    QString root;
    QList<QUrl> requested;
    bool resourceExists(const QUrl& url){return QFile::exists(url.isLocalFile()?url.toLocalFile():root+url.path());}
    ResourceRequest* createResourceRequest(QObject*,const QUrl& url,bool,int,const QString&){
        requested.append(url);auto* request=new ResourceRequest;request->setParent(this);
        request->file=url.isLocalFile()?url.toLocalFile():root+url.path();return request;
    }
};
struct DependencyManager {template<class T>static T* get(){static T service;return &service;}};
// Renderer and unrelated transform/sampler fields are explicit boundaries. Texture/Material/MeshPart declarations are production.
namespace graphics {
struct MaterialKey {enum OpacityMapMode {OPACITY_MAP_BLEND};};
struct Material {
    void setEmissive(glm::vec3){} void setAlbedo(glm::vec3){} void setMetallic(float){} void setRoughness(float){} void setOpacity(float){}
    static float shininessToRoughness(float value){return value;}
};
using MaterialPointer=std::shared_ptr<Material>;
}
struct Transform {};
struct Sampler {};
#include <image/ColorChannel.h>
#include "obj-hfm-values.inc"
struct ModelExtents {void reset(){} void addPoint(glm::vec3){}};
struct HFMCluster {int jointIndex;glm::mat4 inverseBindMatrix;};
struct HFMJoint {int parentIndex;float distanceToParent;glm::vec3 translation,rotationMin,rotationMax;QString name;bool isSkeletonJoint;};
struct HFMMesh {
    int meshIndex;QVector<HFMMeshPart> parts;QVector<glm::vec3> vertices,colors,normals;QVector<glm::vec2> texCoords;
    QVector<HFMCluster> clusters;ModelExtents meshExtents;
};
struct HFMModel {
    using Pointer=std::shared_ptr<HFMModel>;
    QVector<HFMMesh> meshes;QVector<HFMJoint> joints;QHash<QString,int> jointIndices;QHash<QString,HFMMaterial> materials;ModelExtents meshExtents;
};
#define PROFILE_RANGE_EX(...)
#include "obj-declarations.inc"
class OBJSerializer {
public:
#include "obj-fields.inc"
    hifi::URL _url;
    QHash<hifi::ByteArray,bool> librariesSeen;
    int _partCounter {0};
#include "obj-methods.inc"
};
class NetworkMaterial {public:static QUrl getTextureUrl(const QUrl&,const HFMTexture&);};
