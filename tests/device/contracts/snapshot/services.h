// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QGuiApplication>
#include <QImage>
#include <QSharedPointer>
#include <QTimer>
#include <QMutex>
#include <QHash>
#include <QUrl>
#include <QFile>
#include <QTemporaryFile>
#include <QVariant>
#include <QPointer>
#include <glm/glm.hpp>
#include <glm/gtc/quaternion.hpp>
#include <QRegularExpression>
#include <functional>
#include <queue>
#include <array>
#include <stdexcept>
#include "SnapshotCapture.h"
namespace Setting {
template<class T> struct Handle {
    Handle(const char*, T initial = {}) : value(initial) {}
    T value; T get(T = {}) const { return value; } void set(T v) { value = v; }
};
}
class WindowScriptingInterface : public QObject {
    Q_OBJECT
public:
    void takeSnapshot(bool,bool,float,const QString&,const QString&);
    void takeSecondaryCamera360Snapshot(const glm::vec3&,const bool&,const bool&,const QString&,const QString&);
signals:
    void processingGifStarted(QString);
    void processingGifCompleted(QString);
    void snapshotShared(bool,QString);
    void stillSnapshotTaken(QString,bool);
    void snapshot360Taken(QString,bool);
};
class SnapshotUploader;
class SnapshotMetaData { public: QUrl getURL() { return {}; } };
class Snapshot : public QObject {
    Q_OBJECT
public:
    Snapshot();
    bool nativeReviewEnabled() const { return true; }
    QString getSnapshotsLocation();
    QUrl snapshotFileUrl(const QString&) const;
    QFile* savedFileForSnapshot(QImage& shot,bool temporary,const QString& filename=QString(),const QString& pathname=QString());
    Setting::Handle<QString> _snapshotFormat {"format"}, _snapshotsLocation {"location"};
    SnapshotCapture beginCapture(const QString& request);
    void captureStatus(const SnapshotCapture&,const QString& phase,const QString& path={},const QString& error={});
    void cancelCapture(const QString& request);
    static QImage convertToCubemap(std::array<QImage,6>,SnapshotCapture);
    static QImage convertToEquirectangular(std::array<QImage,6>,SnapshotCapture);
    void restoreSecondaryCamera();
    QString saveSnapshot(QImage image,const QString& filename,const QString& pathname=QString());
    void save360Snapshot(const glm::vec3&,const bool&,const bool&,const QString&,const SnapshotCapture& capture={});
    void takeNextSnapshot();
    void complete360(const QImage&,const QString&,bool,const SnapshotCapture&);
    QString _snapshotFilename;
    bool _notify360 {false}, _cubemapOutputFormat {false}, _oldEnabled {false};
    qint16 _snapshotIndex {0};
    QVariant _oldAttachedEntityId,_oldOrientation,_oldPosition,_oldMirrorProjection,_oldPortalProjection;
    QVariant _oldvFoV,_oldNearClipPlaneDistance,_oldFarClipPlaneDistance;
    int _oldTextureWidth {0},_oldTextureHeight {0};
    QHash<QString,QPointer<SnapshotUploader>> _uploads;
    bool _uploadContextConnected {false};
    SnapshotMetaData* parseSnapshotData(QString) { return nullptr; }
    void uploadSnapshot(const QString&,const QUrl& href=QUrl());
    void cancelUpload(const QString&);
    void cancelUploads();
    QMutex _captureMutex;
    QHash<QString,SnapshotCapture> _captures;
    SnapshotCapture _capture360;
    QTimer _snapshotTimer;
    bool _taking360Snapshot {false}, _waitingOnSnapshot {false};
    QImage _imageArray[6];
signals:
    void captureStatusChanged(QString request,QString phase,QString path,QString error);
    void uploadStatusChanged(QString path,QString status,QString error);
};
class SecondaryCameraJobConfig : public QObject {
public:
    int textureWidth {640},textureHeight {480};bool enabled {false};
    bool isEnabled() const { return enabled; }
    void enableSecondaryCameraRenderConfigs(bool value) { enabled=value; }
    void resetSizeSpectatorCamera(int width,int height) { textureWidth=width;textureHeight=height; }
    void setPosition(glm::vec3 position) { setProperty("position",QVariantList{position.x,position.y,position.z}); }
    void setOrientation(glm::quat rotation) { setProperty("orientation",QVariantList{rotation.w,rotation.x,rotation.y,rotation.z}); }
};
struct RenderConfig { SecondaryCameraJobConfig camera; QObject* getConfig(QString) { return &camera; } };
struct RenderEngine { RenderConfig config; RenderConfig* getConfiguration() { return &config; } };
class RenderApplication : public QGuiApplication {
public:
    using QGuiApplication::QGuiApplication;
    struct Reticle { void setVisible(bool) {} void setAllowMouseCapture(bool) {} } reticle;
    struct Compositor { Reticle* reticle; Reticle* getReticleInterface() { return reticle; } } compositor {&reticle};
    Compositor& getApplicationCompositor() { return compositor; }
    RenderEngine engine;
    RenderEngine* getRenderEngine() { return &engine; }
    void takeSnapshot(bool,bool,float,const QString&,const QString&);
    void takeSecondaryCamera360Snapshot(const glm::vec3&,const bool&,const bool&,const QString&,const QString&);
    using Operation = std::tuple<std::function<void(const QImage&)>,float,bool>;
    std::queue<Operation> operators;
    void addSnapshotOperator(Operation op) { operators.push(std::move(op)); }
    void postLambdaEvent(std::function<void()> action) { QMetaObject::invokeMethod(this,std::move(action),Qt::QueuedConnection); }
};
#undef qApp
#define qApp static_cast<RenderApplication*>(QCoreApplication::instance())
#include <NumericalConstants.h>
template<class T> QSharedPointer<T>& service() { static QSharedPointer<T> value(new T); return value; }
struct DependencyManager { template<class T> static QSharedPointer<T> get() { return service<T>(); } };

struct OffscreenUi { static QString getExistingDirectory(QObject*,const char*,QString) { throw std::runtime_error("Desktop directory chooser used by native capture"); } };

struct TestScriptingInterface { static TestScriptingInterface* getInstance() { static TestScriptingInterface test; return &test; } QString getTestResultsLocation() { return {}; } };
