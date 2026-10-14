// Copyright 2026 Overte contributors.
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <QObject>
#include <QStringList>

class NativeSnapshotAdapter : public QObject {
    Q_OBJECT
    Q_PROPERTY(QStringList capabilities READ capabilities CONSTANT)
    Q_PROPERTY(bool busy READ busy NOTIFY stateChanged)
    Q_PROPERTY(QString error READ error NOTIFY stateChanged)
public:
    explicit NativeSnapshotAdapter(QObject* parent = nullptr);
    ~NativeSnapshotAdapter() override;
    QStringList capabilities() const { return { "save", "share" }; }
    bool busy() const { return _request != 0; }
    QString error() const { return _error; }
    Q_INVOKABLE QString request(const QString& canonicalPath, const QString& action);
    Q_INVOKABLE void cancel(const QString& ticket);
    void acceptCompletion(qint64 ticket, const QString& status, const QString& error);
signals:
    void stateChanged();
    void completed(const QString& ticket, const QString& status, const QString& error);
private:
    void complete(qint64 ticket, const QString& status, const QString& error);
    qint64 _handle { 0 }, _request { 0 };
    QString _error;
};
