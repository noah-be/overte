//
//  SnapshotUploader.h
//  interface/src/ui
//
//  Created by Howard Stearns on 8/22/2016
//  Copyright 2016 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#ifndef hifi_SnapshotUploader_h
#define hifi_SnapshotUploader_h

#include <QObject>
#include <QtNetwork/QNetworkReply>
#include <QtCore/QUrl>
#include <RequestCancellation.h>

class SnapshotUploader : public QObject {
    Q_OBJECT
public:
    SnapshotUploader(QUrl inWorldLocation, QString pathname);
    overte::network::RequestTicket nextTicket() { return _requests.next(); }
signals:
    void finished(const QString& path, const QString& status, const QString& error);
public slots:
    void cancel();
    void uploadSuccess(QNetworkReply* reply);
    void uploadFailure(QNetworkReply* reply);
    void createStorySuccess(QNetworkReply* reply);
    void createStoryFailure(QNetworkReply* reply);
private:
    QUrl _inWorldLocation;
    QString _pathname;
    overte::network::RequestScope _requests;
    bool _finished { false };
    void complete(bool error, const QString& reply);
};
#endif // hifi_SnapshotUploader_h
