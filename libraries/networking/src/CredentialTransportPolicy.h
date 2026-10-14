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

inline bool requestCarriesCredentials(const QNetworkRequest& request) {
    return request.hasRawHeader("Authorization") || !request.url().userInfo().isEmpty();
}

inline bool credentialRequestTransportAllowed(const QNetworkRequest& request) {
    auto endpoint = request.url();
    // Script XMLHttpRequest's explicit username/password arguments use URL
    // user information. Preserve that HTTPS API while rejecting cleartext.
    endpoint.setUserInfo(QString());
    return credentialTransportAllowed(endpoint);
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
#if QT_VERSION >= QT_VERSION_CHECK(5, 15, 0)
            // Qt5.15 bridges errorOccurred to its legacy error signal itself.
            // Emitting both would deliver existing error receivers twice.
            emit errorOccurred(error());
#else
            QMetaObject::invokeMethod(this, "error", Qt::DirectConnection,
                Q_ARG(QNetworkReply::NetworkError, QNetworkReply::error()));
#endif
            if (surviving) { emit surviving->finished(); }
        });
    }
    void abort() override {}
protected:
    qint64 readData(char*, qint64) override { return -1; }
};

// The thread-local generic manager used by scripts, asset requests and the
// close-event sender also enforces the rule for explicit Authorization or
// URL credentials. Anonymous HTTP retains QNetworkAccessManager behavior.
class CredentialNetworkAccessManager final : public QNetworkAccessManager {
public:
    using QNetworkAccessManager::QNetworkAccessManager;
protected:
    QNetworkReply* createRequest(Operation operation, const QNetworkRequest& request,
            QIODevice* outgoingData = nullptr) override {
        if (requestCarriesCredentials(request)) {
            if (!credentialRequestTransportAllowed(request)) {
                return new RejectedCredentialReply(*this, operation);
            }
            auto secured = request;
            secured.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
            return QNetworkAccessManager::createRequest(operation, secured, outgoingData);
        }
        return QNetworkAccessManager::createRequest(operation, request, outgoingData);
    }
};

inline QNetworkReply* postCredentials(QNetworkAccessManager& manager,
        const QNetworkRequest& request, const QByteArray& body) {
    if (!credentialTransportAllowed(request.url())) {
        return new RejectedCredentialReply(manager, QNetworkAccessManager::PostOperation);
    }
    auto secured = request;
    secured.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    return manager.post(secured, body);
}

inline QNetworkReply* getCredentials(QNetworkAccessManager& manager,
        const QNetworkRequest& request) {
    if (!credentialTransportAllowed(request.url())) {
        return new RejectedCredentialReply(manager, QNetworkAccessManager::GetOperation);
    }
    auto secured = request;
    secured.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    return manager.get(secured);
}

inline QNetworkReply* putCredentials(QNetworkAccessManager& manager,
        const QNetworkRequest& request, const QByteArray& body) {
    if (!credentialTransportAllowed(request.url())) {
        return new RejectedCredentialReply(manager, QNetworkAccessManager::PutOperation);
    }
    auto secured = request;
    secured.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    return manager.put(secured, body);
}

} }
