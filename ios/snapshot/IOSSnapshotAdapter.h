// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QObject>
#include <QStringList>
#include <memory>

namespace overte::ios {
struct IOSSnapshotNativeOperation;
class IOSSnapshotAdapter : public QObject {
    Q_OBJECT
    Q_PROPERTY(QStringList capabilities READ capabilities CONSTANT)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
public:
    explicit IOSSnapshotAdapter(QObject* parent=nullptr);
    ~IOSSnapshotAdapter() override;
    QStringList capabilities() const { return {QStringLiteral("save"),QStringLiteral("share")}; }
    bool busy() const { return bool(_operation); }
    QString error() const { return _error; }
    Q_INVOKABLE QString request(const QString& canonicalPath,const QString& action);
    Q_INVOKABLE void cancel(const QString& ticket);
    void nativeFinished(const std::shared_ptr<IOSSnapshotNativeOperation>&,const QString& status,const QString& error);
signals:
    void changed();
    void completed(const QString& ticket,const QString& status,const QString& error);
private:
    std::shared_ptr<IOSSnapshotNativeOperation> _operation;
    QString _error;
};
} // namespace overte::ios
