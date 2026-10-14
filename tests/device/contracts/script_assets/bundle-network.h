// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
// Explicit server boundary: actual AssetUpload reads/hashes files and this peer stores their bytes.
#pragma once
#include <QCryptographicHash>
#include <QTemporaryDir>
#include <QDir>
#include <QUrl>
#include <QUuid>
#include <QSet>
#include <QFileInfo>
#include <QFile>
#include <QTimer>
#include <QLoggingCategory>
#include <QHash>
#include <functional>
#include "AssetUpload.h"
Q_DECLARE_LOGGING_CATEGORY(asset_client)
namespace AssetUtils {
enum class AssetServerError { NoError, AssetTooLarge, PermissionDenied, FileOperationFailed };
inline QByteArray hashData(const QByteArray& data) { return QCryptographicHash::hash(data, QCryptographicHash::Sha256); }
inline QUrl getATPUrl(const QString& hash) { return QUrl("atp:" + hash); }
inline void saveToCache(const QUrl&, const QByteArray&) { } // ResourceCache is outside this host boundary.
}
struct NodeList : QObject {
    Q_OBJECT
public:
    bool write {false};
    bool getThisNodeCanWriteAssets() { return write; }
    QUuid getSessionUUID() { return QUuid("11111111-2222-3333-4444-555555555555"); }
    void revokeWrites() { write=false; emit canWriteAssetsChanged(false); }
signals: void canWriteAssetsChanged(bool);
};
struct DependencyManager { template<class T> static T* get() { static T service; return &service; } };
class SetMappingRequest : public QObject {
    Q_OBJECT
public:
    QString path, hash, error;
    QString getPath() const { return path; }
    QString getErrorString() const { return error; }
    void start();
signals: void finished(SetMappingRequest* request);
};
class AssetClient {
public:
    QTemporaryDir store;
    QHash<QString,QByteArray> blobs;
    QHash<QString,QString> mappings;
    QStringList published;
    int uploads {0};
    bool holdUploads {false};
    QList<std::function<void()>> pending;
    int failAt {-1};
    AssetUpload* createUpload(const QString& path) { return new AssetUpload(path); }
    SetMappingRequest* createSetMappingRequest(const QString& path,const QString& hash) {
        auto* r=new SetMappingRequest; r->path=path; r->hash=hash; return r;
    }
    void uploadAsset(const QByteArray& data, std::function<void(bool,AssetUtils::AssetServerError,const QString&)> done) {
        const auto hash=QString::fromLatin1(AssetUtils::hashData(data).toHex());
        ++uploads; blobs[hash]=data;
        auto reply=[done,hash]{done(true,AssetUtils::AssetServerError::NoError,hash);};
        if(holdUploads) pending.append(reply); else QTimer::singleShot(0,reply);
    }
};
inline void SetMappingRequest::start() {
    QTimer::singleShot(0,this,[this]{
        auto* peer=DependencyManager::get<AssetClient>();
        if (peer->published.size()==peer->failAt) error="Server mapping failure";
        else {
            QDir().mkpath(QFileInfo(peer->store.path()+path).absolutePath());
            QFile f(peer->store.path()+path); if(!f.open(QFile::WriteOnly)||f.write(peer->blobs.value(hash))!=peer->blobs.value(hash).size()) error="Peer write failure";
            else {peer->mappings[path]=hash;peer->published.append(path);}
        }
        emit finished(this);
    });
}
