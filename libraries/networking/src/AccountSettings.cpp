//
//  AccountSettings.cpp
//  libraries/networking/src
//
//  Created by Clement Brisset on 9/12/19.
//  Copyright 2019 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "AccountSettings.h"

#include <QJsonDocument>
#include <QJsonObject>

#include "NetworkLogging.h"
#include "SharedUtil.h"

static QString HOME_LOCATION_KEY { "home_location" };

QJsonObject AccountSettings::pack() {
    return snapshot().data;
}

AccountSettings::Snapshot AccountSettings::snapshot() const {
    QReadLocker lock(&_settingsLock);
    return { QJsonObject { { HOME_LOCATION_KEY, _homeLocation } }, _lastChangeTimestamp };
}

void AccountSettings::unpack(QJsonObject data) {
    QWriteLocker lock(&_settingsLock);
    unpackLocked(data);
}

bool AccountSettings::unpackIfUnchanged(const QJsonObject& data, quint64 expectedTimestamp,
                                      quint64& appliedTimestamp) {
    QWriteLocker lock(&_settingsLock);
    if (_lastChangeTimestamp != expectedTimestamp) { return false; }
    unpackLocked(data);
    appliedTimestamp = _lastChangeTimestamp;
    return true;
}

void AccountSettings::advanceTimestampLocked() {
    // Clock resolution/adjustments must not make different snapshots identical.
    // Never wrap and accidentally accept a previously issued snapshot.
    if (_lastChangeTimestamp == std::numeric_limits<quint64>::max()) {
        throw std::overflow_error("Account settings revision exhausted");
    }
    _lastChangeTimestamp = std::max(_lastChangeTimestamp + 1, usecTimestampNow());
}

void AccountSettings::unpackLocked(const QJsonObject& data) {
    advanceTimestampLocked();

    auto it = data.find(HOME_LOCATION_KEY);
    _homeLocationState = it != data.end() && it->isString() ? Loaded : NotPresent;
    _homeLocation = _homeLocationState == Loaded ? it->toString() : "";
    _hasLocalChanges = false;
}

void AccountSettings::setHomeLocation(QString homeLocation) {
    QWriteLocker lock(&_settingsLock);
    if (homeLocation != _homeLocation || _homeLocationState != Loaded) {
        // Explicit local intent while loading (or choosing an absent value)
        // supersedes the pending server snapshot, even for equal text.
        advanceTimestampLocked();
        _hasLocalChanges = true;
    }
    _homeLocation = homeLocation;
    _homeLocationState = Loaded;
}

void AccountSettings::startedLoading() {
    QWriteLocker lock(&_settingsLock);
    if (_homeLocationState != Loading) { _stateBeforeDownload = _homeLocationState; }
    _homeLocationState = Loading;
}

bool AccountSettings::beginDownload(quint64& requestedTimestamp) {
    QWriteLocker lock(&_settingsLock);
    if (_hasLocalChanges) { return false; }
    requestedTimestamp = _lastChangeTimestamp;
    if (_homeLocationState != Loading) { _stateBeforeDownload = _homeLocationState; }
    _homeLocationState = Loading;
    return true;
}

void AccountSettings::acknowledgeSnapshot(quint64 timestamp) {
    QWriteLocker lock(&_settingsLock);
    if (timestamp == _lastChangeTimestamp) { _hasLocalChanges = false; }
}

void AccountSettings::downloadFailed(quint64 requestedTimestamp) {
    QWriteLocker lock(&_settingsLock);
    if (!_hasLocalChanges && _lastChangeTimestamp == requestedTimestamp && _homeLocationState == Loading) {
        _homeLocationState = _stateBeforeDownload;
    }
}

void AccountSettings::loggedOut() {
    QWriteLocker lock(&_settingsLock);
    advanceTimestampLocked();
    _homeLocation.clear();
    _hasLocalChanges = false;
    _homeLocationState = LoggedOut;
}
