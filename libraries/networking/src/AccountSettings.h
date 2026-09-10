//
//  AccountSettings.h
//  libraries/networking/src
//
//  Created by Clement Brisset on 9/12/19.
//  Copyright 2019 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#ifndef hifi_AccountSettings_h
#define hifi_AccountSettings_h

#include <QJsonObject>
#include <QReadWriteLock>
#include <QString>
#include <algorithm>
#include <limits>
#include <stdexcept>

class AccountSettings {
public:
    enum State {
        LoggedOut,
        Loading,
        Loaded,
        NotPresent
    };

    void loggedOut();
    void startedLoading();
    bool beginDownload(quint64& requestedTimestamp);
    void downloadFailed(quint64 requestedTimestamp);
    void acknowledgeSnapshot(quint64 timestamp);
    quint64 lastChangeTimestamp() const { QReadLocker lock(&_settingsLock); return _lastChangeTimestamp; }

    struct Snapshot {
        QJsonObject data;
        quint64 timestamp;
    };
    Snapshot snapshot() const;

    QJsonObject pack();
    void unpack(QJsonObject data);
    bool unpackIfUnchanged(const QJsonObject& data, quint64 expectedTimestamp, quint64& appliedTimestamp);

    State homeLocationState() const { QReadLocker lock(&_settingsLock); return _homeLocationState; }
    QString getHomeLocation() const { QReadLocker lock(&_settingsLock); return _homeLocation; }
    void setHomeLocation(QString homeLocation);

private:
    void advanceTimestampLocked();
    void unpackLocked(const QJsonObject& data);
    mutable QReadWriteLock _settingsLock;
    quint64 _lastChangeTimestamp { 0 };
    bool _hasLocalChanges { false };

    State _homeLocationState { LoggedOut };
    State _stateBeforeDownload { LoggedOut };
    QString _homeLocation;
};

#endif /* hifi_AccountSettings_h */
