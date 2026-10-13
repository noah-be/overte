//
//  SnapshotAnimated.cpp
//  interface/src/ui
//
//  Created by Zach Fox on 11/14/16.
//  Copyright 2016 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "SnapshotAnimated.h"
#include "Snapshot.h"
#include <QDateTime>
#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QImageReader>
#include <QFutureWatcher>
#include <cstdio>
#include <QtConcurrent/QtConcurrentRun>
#include <algorithm>
#include <cmath>

QTimer* SnapshotAnimated::snapshotAnimatedTimer = nullptr;
qint64 SnapshotAnimated::snapshotAnimatedTimestamp = 0;
qint64 SnapshotAnimated::snapshotAnimatedFirstFrameTimestamp = 0;
bool SnapshotAnimated::snapshotAnimatedTimerRunning = false;
bool SnapshotAnimated::snapshotFramePending = false;
QString SnapshotAnimated::snapshotAnimatedPath;
QString SnapshotAnimated::snapshotStillPath;
QVector<QImage> SnapshotAnimated::snapshotAnimatedFrameVector;
QVector<qint64> SnapshotAnimated::snapshotAnimatedFrameDelayVector;
float SnapshotAnimated::aspectRatio;
QSharedPointer<WindowScriptingInterface> SnapshotAnimated::snapshotAnimatedDM;
SnapshotCapture SnapshotAnimated::snapshotCapture;
SnapshotCapture SnapshotAnimated::encodingCapture;

Setting::Handle<bool> SnapshotAnimated::alsoTakeAnimatedSnapshot("alsoTakeAnimatedSnapshot", true);
Setting::Handle<float> SnapshotAnimated::snapshotAnimatedDuration("snapshotAnimatedDuration", SNAPSNOT_ANIMATED_DURATION_SECS);

void SnapshotAnimated::saveSnapshotAnimated(QString pathStill, float ratio, QSharedPointer<WindowScriptingInterface> dm,
                                           const SnapshotCapture& request) {
    if (isAlreadyTakingSnapshotAnimated()) { return; }
    snapshotCapture = request ? request : DependencyManager::get<Snapshot>()->beginCapture({});
    if (!snapshotCapture || !snapshotCapture->current()) { snapshotCapture.reset(); return; }
    clearTempVariables();
    snapshotFramePending = false;
    aspectRatio = ratio;
    snapshotAnimatedDM = dm;
    snapshotStillPath = pathStill;
    const QFileInfo still(pathStill);
    snapshotAnimatedPath = still.dir().filePath(still.completeBaseName() + ".gif");
    snapshotAnimatedTimer = new QTimer(qApp);
    snapshotAnimatedTimer->setTimerType(Qt::PreciseTimer);
    QObject::connect(snapshotAnimatedTimer, &QTimer::timeout, qApp, captureFrames);
    snapshotAnimatedTimerRunning = true;
    snapshotAnimatedTimer->start(SNAPSNOT_ANIMATED_FRAME_DELAY_MSEC);
}

void SnapshotAnimated::cancelCapture(const SnapshotCapture& request) {
    if (snapshotCapture != request) { return; }
    if (snapshotAnimatedTimer) { snapshotAnimatedTimer->stop(); snapshotAnimatedTimer->deleteLater(); snapshotAnimatedTimer = nullptr; }
    snapshotAnimatedTimerRunning = false;
    snapshotFramePending = false;
    clearTempVariables();
    snapshotCapture.reset();
}

void SnapshotAnimated::captureFrames() {
    const auto request = snapshotCapture;
    if (!request || !request->current()) { cancelCapture(request); return; }
    if (snapshotAnimatedTimerRunning) {
        if (snapshotFramePending) { return; } // At most one render operator outstanding.
        snapshotFramePending = true;
        qApp->addSnapshotOperator(std::make_tuple([request](const QImage& snapshot) {
            qApp->postLambdaEvent([request, snapshot] {
                if (snapshotCapture != request || !request->current()) { return; }
                snapshotFramePending = false;
                if (snapshot.isNull()) {
                    DependencyManager::get<Snapshot>()->captureStatus(request, "error", {}, "empty-frame");
                    cancelCapture(request); return;
                }
                const QImage frame = snapshot.scaledToWidth(SNAPSNOT_ANIMATED_WIDTH);
                snapshotAnimatedFrameVector.append(frame);
                const auto now = QDateTime::currentMSecsSinceEpoch();
                const qint64 delay = snapshotAnimatedFirstFrameTimestamp == 0 ? SNAPSNOT_ANIMATED_FRAME_DELAY_MSEC / 10 :
                    std::max<qint64>(1, (now - snapshotAnimatedTimestamp) / 10);
                snapshotAnimatedFrameDelayVector.append(delay);
                if (snapshotAnimatedFirstFrameTimestamp == 0) { snapshotAnimatedFirstFrameTimestamp = now; }
                snapshotAnimatedTimestamp = now;
                const float configured = snapshotAnimatedDuration.get();
                // Match the existing preferences' supported one-to-five-second range.
                const float duration = std::isfinite(configured) ? std::clamp(configured, 1.0f, 5.0f) : 3.0f;
                if (now - snapshotAnimatedFirstFrameTimestamp >= duration * MSECS_PER_SECOND ||
                        snapshotAnimatedFrameVector.size() >= 5 * SNAPSNOT_ANIMATED_TARGET_FRAMERATE + 1) {
                    snapshotAnimatedTimerRunning = false;
                }
            });
        }, aspectRatio, true));
        return;
    }
    if (snapshotFramePending) { return; }
    const auto path = snapshotAnimatedPath;
    const auto dm = snapshotAnimatedDM;
    const auto still = snapshotStillPath;
    const auto frames = snapshotAnimatedFrameVector;
    const auto delays = snapshotAnimatedFrameDelayVector;
    if (snapshotAnimatedTimer) { snapshotAnimatedTimer->stop(); snapshotAnimatedTimer->deleteLater(); snapshotAnimatedTimer = nullptr; }
    clearTempVariables();
    snapshotCapture.reset();
    encodingCapture = request;
    emit dm->processingGifStarted(still);
    DependencyManager::get<Snapshot>()->captureStatus(request, "processing", still);
    auto watcher = new QFutureWatcher<bool>(qApp);
    QObject::connect(watcher, &QFutureWatcher<bool>::finished, qApp, [watcher, request, path, dm] {
        const bool success = watcher->result();
        watcher->deleteLater();
        if (encodingCapture == request) { encodingCapture.reset(); }
        if (!request->current()) { QFile::remove(path); return; }
        if (!success) { DependencyManager::get<Snapshot>()->captureStatus(request, "error", {}, "gif-save-failed"); return; }
        emit dm->processingGifCompleted(path);
        DependencyManager::get<Snapshot>()->captureStatus(request, "complete", path);
    });
    watcher->setFuture(QtConcurrent::run([frames, delays, path, request] { return processFrames(frames, delays, path, request); }));
}

void SnapshotAnimated::clearTempVariables() {
    snapshotAnimatedFrameVector.clear(); snapshotAnimatedFrameVector.squeeze();
    snapshotAnimatedFrameDelayVector.clear(); snapshotAnimatedFrameDelayVector.squeeze();
    snapshotAnimatedTimestamp = snapshotAnimatedFirstFrameTimestamp = 0;
}

bool SnapshotAnimated::processFrames(QVector<QImage> frames, QVector<qint64> delays, QString path, SnapshotCapture request) {
    if (!request->current()) { return false; }
    bool success = !frames.isEmpty() && frames.size() == delays.size();
    GifWriter writer {};
    if (success) { success = GifBegin(&writer, qPrintable(path), frames[0].width(), frames[0].height(), 1); }
    if (success) {
        for (int i = 0; i < frames.size(); ++i) {
            if (!request->current() || frames[i].size() != frames[0].size()) { success = false; break; }
            const auto rgba = frames[i].convertToFormat(QImage::Format_RGBA8888);
            if (!GifWriteFrame(&writer, rgba.constBits(), rgba.width(), rgba.height(), delays[i])) { success = false; break; }
        }
        if (std::ferror(writer.f)) { success = false; }
        if (std::fflush(writer.f) != 0) { success = false; }
        // GifEnd closes the file and frees the writer even on cancellation.
        if (!GifEnd(&writer)) { success = false; }
    }
    QFile encoded(path);
    const bool complete = encoded.open(QFile::ReadOnly) && encoded.size() > 0 && encoded.seek(encoded.size() - 1) && encoded.read(1) == QByteArray(1, char(0x3b));
    encoded.close();
    success = success && complete && QImageReader(path).canRead();
    if (!success || !request->current()) { QFile::remove(path); }
    return success && request->current();
}
