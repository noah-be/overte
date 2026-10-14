// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QPointer>
#include <QTimer>
#include <QUrl>

namespace overte { namespace network {

inline bool credentialTransportAllowed(const QUrl& url) {
    return url.isValid() && !url.isRelative() && !url.host().isEmpty() &&
        url.scheme().compare(QStringLiteral("https"), Qt::CaseInsensitive) == 0 &&
        url.userInfo().isEmpty();
}

// Deliver the existing asynchronous error path without opening a socket or
// retaining a credential body. The reply owns its queued terminal callback.
class RejectedCredentialReply final : public QNetworkReply {
public:
    explicit RejectedCredentialReply(QNetworkAccessManager& manager,
            QNetworkAccessManager::Operation operation) : QNetworkReply(&manager) {
        setOperation(operation);
        setError(QNetworkReply::ContentAccessDenied, QStringLiteral("Credential requests require HTTPS"));
        setFinished(true);
        open(QIODevice::ReadOnly | QIODevice::Unbuffered);
        QTimer::singleShot(0, this, [this] {
            const QPointer<RejectedCredentialReply> surviving(this);
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
            // Existing Qt5 callers still connect the legacy error signal.
            QMetaObject::invokeMethod(this, "error", Qt::DirectConnection,
                Q_ARG(QNetworkReply::NetworkError, QNetworkReply::error()));
            if (!surviving) { return; }
#endif
#if QT_VERSION >= QT_VERSION_CHECK(5, 15, 0)
            emit errorOccurred(error());
#endif
            if (surviving) { emit surviving->finished(); }
        });
    }
    void abort() override {}
protected:
    qint64 readData(char*, qint64) override { return -1; }
};

inline QNetworkReply* postCredentials(QNetworkAccessManager& manager,
        const QNetworkRequest& request, const QByteArray& body) {
    if (!credentialTransportAllowed(request.url())) {
        return new RejectedCredentialReply(manager, QNetworkAccessManager::PostOperation);
    }
    return manager.post(request, body);
}

} }
