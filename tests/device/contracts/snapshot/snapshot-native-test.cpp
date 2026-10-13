// SPDX-License-Identifier: Apache-2.0
#include "services.h"
#include "SnapshotAnimated.h"
#include "SnapshotStorage.h"
#include "SnapshotUploader.h"
#include "upload-services.h"
#include <QTemporaryDir>
#include <QFile>
#include <QImageReader>
#include <QElapsedTimer>
#include <QPainter>
#include <QFutureWatcher>
#include <QtConcurrent/QtConcurrentRun>
#include <glm/glm.hpp>
#include <NumericalConstants.h>
#include "production-360-constants.inc"
#include <QThread>
#include <thread>
#include <stdexcept>
#include <iostream>
#include <QDateTime>
#include "production-storage-constants.inc"
#include "production-capture.inc"
#include "production-application.inc"
#include "production-window.inc"
#include "services.moc"
#include "SnapshotUploader.moc"
#include "upload-services.moc"
static void verify(bool value, int line) { if (!value) { throw std::runtime_error("Snapshot production contract failed at line " + std::to_string(line)); } }
#define require(value) verify(bool(value),__LINE__)
static void drain() { QCoreApplication::processEvents(); QCoreApplication::sendPostedEvents(nullptr,QEvent::DeferredDelete); }
int main(int argc,char** argv) {
    RenderApplication app(argc,argv);
    QCoreApplication::setOrganizationName("OverteContract");QCoreApplication::setApplicationName("Snapshot");
    QStandardPaths::setTestModeEnabled(false);
    QTemporaryDir temporary;require(temporary.isValid());
    qputenv("XDG_DATA_HOME",temporary.path().toUtf8());
    const auto root=overte::snapshot::storageRoot();require(QDir().mkpath(root));
    QImage red(24,24,QImage::Format_RGBA8888);red.fill(Qt::red);
    QImage blue=red;blue.fill(Qt::blue);
    auto nativeStorage=DependencyManager::get<Snapshot>();
    QFile* saved=nativeStorage->savedFileForSnapshot(red,false,"native.png");require(saved);
    const auto nativeFile=saved->fileName();delete saved;
    require(QImage(nativeFile).pixelColor(0,0)==QColor(Qt::red));
    require(overte::snapshot::exportPath(nativeFile)==QFileInfo(nativeFile).canonicalFilePath());
    require(!nativeStorage->savedFileForSnapshot(red,false,"../escape.png"));
    require(!nativeStorage->savedFileForSnapshot(red,false,"bad\\escape.png"));
    QImage empty;require(!nativeStorage->savedFileForSnapshot(empty,false,"empty.png"));require(!QFile::exists(root+"/empty.png"));
    const auto still=root+"/Photo #?.png";require(red.save(still));
    require(overte::snapshot::exportPath(still,root)==QFileInfo(still).canonicalFilePath());
    require(QImage(overte::snapshot::exportPath(still,root)).pixelColor(0,0)==QColor(Qt::red));
    require(nativeStorage->snapshotFileUrl(still).toLocalFile()==QFileInfo(still).canonicalFilePath());
    require(nativeStorage->snapshotFileUrl(temporary.path()+"/outside.png").isEmpty());
    require(overte::snapshot::exportPath(root+"/../Snapshots/Photo #?.png",root).isEmpty());
    require(overte::snapshot::exportPath(still,root+"/missing").isEmpty());
    require(QFile::link(still,root+"/alias.png"));require(overte::snapshot::exportPath(root+"/alias.png",root).isEmpty());
    require(QDir().mkpath(root+"/sub"));require(red.save(root+"/sub/photo.png"));
    require(overte::snapshot::exportPath(root+"/sub/photo.png",root).isEmpty());
    require(red.save(temporary.path()+"/outside.png"));require(overte::snapshot::exportPath(temporary.path()+"/outside.png",root).isEmpty());
    QFile large(root+"/large.gif");require(large.open(QFile::WriteOnly));require(large.resize(256LL*1024*1024+1));large.close();
    require(overte::snapshot::exportPath(large.fileName(),root).isEmpty());
    const auto gif=root+"/animation.gif";
    auto capture=std::make_shared<SnapshotCaptureRequest>("encode");
    require(SnapshotAnimated::processFrames({red,blue},{4,7},gif,capture));
    QImageReader reader(gif);require(reader.imageCount()==2);
    require(reader.read().pixelColor(0,0)==QColor(Qt::red));require(reader.nextImageDelay()==40);
    require(reader.read().pixelColor(0,0)==QColor(Qt::blue));require(reader.nextImageDelay()==70);
    require(overte::snapshot::exportPath(gif,root)==QFileInfo(gif).canonicalFilePath());
    require(!SnapshotAnimated::processFrames({red},{},root+"/bad.gif",capture));
    require(!QFile::exists(root+"/bad.gif"));
    require(!SnapshotAnimated::processFrames({red},{4},temporary.path()+"/missing/bad.gif",capture));
    capture->cancel();require(!SnapshotAnimated::processFrames({red},{4},root+"/cancel.gif",capture));
    require(!QFile::exists(root+"/cancel.gif"));
    for(int i=0;i<500;++i) {
        SnapshotCaptureRequest race("race");bool cancelled=false,completed=false;
        std::thread worker([&]{completed=race.finish();});cancelled=race.cancel();worker.join();
        require(cancelled!=completed);require(!race.current());require(!race.finish());require(!race.cancel());
    }
    std::array<QImage,6> faces;
    const QColor colors[6]={Qt::red,Qt::green,Qt::blue,Qt::yellow,Qt::cyan,Qt::magenta};
    for(int i=0;i<6;++i){faces[i]=QImage(2048,2048,QImage::Format_RGB32);faces[i].fill(colors[i]);}
    auto panoramaRequest=std::make_shared<SnapshotCaptureRequest>("panorama");
    {
        const auto cube=Snapshot::convertToCubemap(faces,panoramaRequest);
        require(cube.size()==QSize(8192,6144));
        const QPoint cells[6]={{1,2},{1,1},{0,1},{3,1},{2,1},{1,0}};
        for(int i=0;i<6;++i){require(cube.pixelColor(cells[i]*2048+QPoint(10,10))==colors[i]);}
    }
    {
        const auto panorama=Snapshot::convertToEquirectangular(faces,panoramaRequest);
        require(panorama.size()==QSize(8192,4096));
        require(panorama.pixelColor(4096,10)==colors[5]);
        require(panorama.pixelColor(4096,4000)==colors[0]);
        require(panorama.pixelColor(4096,2048)==colors[1]);
    }
    auto cancelledPanorama=std::make_shared<SnapshotCaptureRequest>("cancel-panorama");
    QImage cancelledImage;
    std::thread conversion([&]{cancelledImage=Snapshot::convertToEquirectangular(faces,cancelledPanorama);});
    QThread::msleep(5);cancelledPanorama->cancel();conversion.join();require(cancelledImage.isNull());
    faces={};
    auto snapshots=DependencyManager::get<Snapshot>();
    int terminals=0;QString phase;
    QObject::connect(snapshots.data(),&Snapshot::captureStatusChanged,[&](QString,QString status,QString,QString){
        phase=status;if(status=="complete"||status=="error"||status=="cancelled"){++terminals;}
    });
    auto old=snapshots->beginCapture("render-old");require(bool(old));
    SnapshotAnimated::saveSnapshotAnimated(still,1.0f,DependencyManager::get<WindowScriptingInterface>(),old);
    SnapshotAnimated::captureFrames();require(app.operators.size()==1);
    for(int i=0;i<30;++i) { SnapshotAnimated::captureFrames(); }
    require(app.operators.size()==1); // bounded even if the renderer stalls
    snapshots->cancelCapture(old->id);require(!old->current());drain();
    require(terminals==1 && phase=="cancelled");require(!SnapshotAnimated::isAlreadyTakingSnapshotAnimated());
    auto queued=std::move(app.operators.front());app.operators.pop();std::get<0>(queued)(red);drain();
    require(SnapshotAnimated::snapshotAnimatedFrameVector.isEmpty());require(terminals==1);
    auto replacement=snapshots->beginCapture("render-new");require(bool(replacement));
    SnapshotAnimated::saveSnapshotAnimated(still,1.0f,DependencyManager::get<WindowScriptingInterface>(),replacement);
    SnapshotAnimated::captureFrames();require(app.operators.size()==1);
    queued=std::move(app.operators.front());app.operators.pop();std::get<0>(queued)(red);drain();
    require(SnapshotAnimated::snapshotAnimatedFrameVector.size()==1);
    SnapshotAnimated::snapshotAnimatedTimerRunning=false;
    SnapshotAnimated::captureFrames();require(SnapshotAnimated::isAlreadyTakingSnapshotAnimated());
    snapshots->cancelCapture(replacement->id);drain();
    QElapsedTimer timeout;timeout.start();
    while(SnapshotAnimated::isAlreadyTakingSnapshotAnimated()&&timeout.elapsed()<5000){drain();QThread::msleep(1);}
    require(!SnapshotAnimated::isAlreadyTakingSnapshotAnimated());require(terminals==2);require(!QFile::exists(root+"/Photo #?.gif"));
    auto stillRequest=snapshots->beginCapture("still");snapshots->captureStatus(stillRequest,"complete",still);
    require(terminals==3);snapshots->cancelCapture("still");drain();require(terminals==3);
    auto invalid=snapshots->beginCapture("../bad");require(!invalid);require(terminals==4);
    auto window=DependencyManager::get<WindowScriptingInterface>();
    window->takeSnapshot(false,false,1.91f,"cancel-api.png","cancel-api");require(app.operators.size()==1);
    auto apiOperation=std::move(app.operators.front());app.operators.pop();
    snapshots->cancelCapture("cancel-api");std::get<0>(apiOperation)(red);drain();
    require(!QFile::exists(root+"/cancel-api.png"));require(terminals==5);
    window->takeSnapshot(false,false,1.91f,"still-api.png","still-api");require(app.operators.size()==1);
    apiOperation=std::move(app.operators.front());app.operators.pop();std::get<0>(apiOperation)(red);drain();
    require(QImage(root+"/still-api.png").pixelColor(0,0)==QColor(Qt::red));require(terminals==6);
    auto& camera=app.engine.config.camera;
    camera.setProperty("position","original-position");camera.setProperty("orientation","original-orientation");
    camera.setProperty("mirrorProjection",true);camera.setProperty("portalProjection",true);
    window->takeSecondaryCamera360Snapshot(glm::vec3(1,2,3),true,false,"cancel-360.png","cancel-360");drain();
    require(camera.enabled&&camera.textureWidth==2048&&camera.textureHeight==2048);
    snapshots->takeNextSnapshot();require(app.operators.size()==1);
    apiOperation=std::move(app.operators.front());app.operators.pop();snapshots->cancelCapture("cancel-360");drain();
    require(!camera.enabled&&camera.textureWidth==640&&camera.textureHeight==480);
    require(camera.property("position").toString()=="original-position");
    require(camera.property("orientation").toString()=="original-orientation");
    require(camera.property("mirrorProjection").toBool()&&camera.property("portalProjection").toBool());
    std::get<0>(apiOperation)(red);drain();require(!QFile::exists(root+"/cancel-360.png"));require(terminals==7);
    window->takeSecondaryCamera360Snapshot(glm::vec3(1,2,3),true,false,"cube-api.png","cube-api");drain();
    QImage face(2048,2048,QImage::Format_RGB32);face.fill(Qt::red);
    for(int i=0;i<6;++i){
        snapshots->takeNextSnapshot();require(app.operators.size()==1);
        apiOperation=std::move(app.operators.front());app.operators.pop();std::get<0>(apiOperation)(face);drain();
    }
    snapshots->takeNextSnapshot();require(!camera.enabled&&camera.textureWidth==640);
    QElapsedTimer cubeDeadline;cubeDeadline.start();
    while(terminals<8&&cubeDeadline.elapsed()<15000){drain();QThread::msleep(1);}
    require(terminals==8&&phase=="complete");require(QImageReader(root+"/cube-api.png").size()==QSize(8192,6144));
    auto accounts=DependencyManager::get<AccountManager>();
    const QByteArray uploadJSON=R"({"data":{"thumbnail_url":"https://example.invalid/thumbnail.png","image_url":"https://example.invalid/photo.png","id":"42","original_image_file_name":"photo.png"}})";
    auto uploader=new SnapshotUploader(QUrl("hifi://place/path"),still);
    FakeReply initial(uploadJSON);
    auto initialTicket=uploader->nextTicket();
    overte::network::watchRequest(&initial,initialTicket);
    uploader->uploadSuccess(&initial);
    require(accounts->calls==1);require(!initialTicket.current());
    require(accounts->lastBody.contains("for_url"));require(accounts->lastBody.contains("snapshot_id"));
    auto storyTicket=accounts->lastTicket;
    FakeReply story(R"({"status":"success","user_story":{"id":42}})");
    overte::network::watchRequest(&story,storyTicket);
    int uploadTerminals=0;QString uploadPhase;
    QObject::connect(uploader,&SnapshotUploader::finished,[&](QString,QString status,QString){++uploadTerminals;uploadPhase=status;});
    uploader->cancel();require(!story.aborted);require(!storyTicket.current());require(uploadTerminals==1&&uploadPhase=="cancelled");
    uploader->createStorySuccess(&story);uploader->uploadSuccess(&initial);
    require(uploadTerminals==1&&accounts->calls==1);
    // Actual watchRequest performs abort only in the reply's owning Qt queue.
    QElapsedTimer abortDeadline;abortDeadline.start();
    while(!story.aborted&&abortDeadline.elapsed()<2000) { QCoreApplication::processEvents();QThread::msleep(1); }
    require(story.aborted);require(story.abortThread==story.thread());
    drain();
    auto cancelledBefore=new SnapshotUploader(QUrl("hifi://place"),still);
    auto beforeTicket=cancelledBefore->nextTicket();cancelledBefore->cancel();
    require(!beforeTicket.current());cancelledBefore->uploadSuccess(&initial);require(accounts->calls==1);drain();
    auto success=new SnapshotUploader(QUrl("hifi://place"),still);
    int successTerminals=0;
    QObject::connect(success,&SnapshotUploader::finished,[&](QString,QString status,QString){require(status=="success");++successTerminals;});
    FakeReply successReply(R"({"status":"success","user_story":{"id":77,"details":{"image_url":"https://example.invalid/photo.png","original_image_file_name":"photo.png"}}})");
    success->createStorySuccess(&successReply);success->cancel();require(successTerminals==1);drain();
    int nativeUploadTerminals=0;
    QObject::connect(snapshots.data(),&Snapshot::uploadStatusChanged,[&](QString,QString status,QString){
        if(status=="error"||status=="cancelled"||status=="success"){++nativeUploadTerminals;}
    });
    snapshots->uploadSnapshot(root+"/nonexistent.png",QUrl("hifi://place"));require(nativeUploadTerminals==1);
    const int uploadsBefore=accounts->calls;
    snapshots->uploadSnapshot(nativeFile,QUrl("hifi://place"));require(accounts->calls==uploadsBefore+1);
    const auto nativeUploadTicket=accounts->lastTicket;
    accounts->logoutComplete();require(!nativeUploadTicket.current());require(nativeUploadTerminals==2);drain();
    require(snapshots->_uploads.isEmpty());
    snapshots->uploadSnapshot(nativeFile,QUrl("hifi://place"));accounts->authEndpointChanged();drain();
    require(nativeUploadTerminals==3&&snapshots->_uploads.isEmpty());
    std::cout<<"PASS: real storage, GIF codec/delays, render bound, cancellation/replacement and atomic terminal race and actual upload/story cancellation\n";
}
