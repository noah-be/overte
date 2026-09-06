//
//  DomainAccountManager.cpp
//  libraries/networking/src
//
//  Created by David Rowe on 23 Jul 2020.
//  Copyright 2020 Vircadia contributors.
//  Copyright 2023 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "DomainAccountManager.h"

#include <QTimer>
#include <QtCore/QJsonObject>
#include <QtCore/QJsonDocument>
#include <QtNetwork/QNetworkRequest>
#include <QtNetwork/QNetworkReply>

#include <DependencyManager.h>
#include <SettingHandle.h>

#include "NetworkingConstants.h"
#include "NetworkAccessManager.h"
#include "NetworkLogging.h"
#include "NodeList.h"
#include "../../../security/redaction/SafeDiagnostics.h"

// FIXME: Generalize to other OAuth2 sources for domain login.

const bool VERBOSE_HTTP_REQUEST_DEBUGGING = false;
namespace {
constexpr qint64 MAX_DOMAIN_AUTH_RESPONSE_BYTES = 1024 * 1024;
}

DomainAccountManager::DomainAccountManager() {
    qRegisterMetaType<overte::network::RequestTicket>();
    connect(this, &DomainAccountManager::loginComplete, this, &DomainAccountManager::sendInterfaceAccessTokenToServer);
}

DomainAccountManager::~DomainAccountManager() {
    invalidatePendingAccessToken();
}

void DomainAccountManager::invalidatePendingAccessToken(LoginOutcome outcome) {
    const auto ticket = _accessTokenRequests.snapshot();
    _accessTokenRequests.next(); // Invalidate BEFORE abort can emit finished.
    const auto context = _accessTokenRequests.snapshot(); // Capture before abort's external callbacks too.
    const auto pending = _pendingAccessTokenReply;
    _pendingAccessTokenReply.clear();
    if (pending) {
        pending->abort();
        pending->deleteLater();
        emit loginRequestFinished(ticket, context, static_cast<int>(outcome));
    }
}

void DomainAccountManager::setClientID(const QString& clientID) {
    if (_currentAuth.clientID == clientID) {
        return;
    }
    invalidatePendingAccessToken();
    _currentAuth.clientID = clientID;
}

void DomainAccountManager::setDomainURL(const QUrl& domainURL) {
    if (domainURL == _currentAuth.domainURL) {
        return;
    }

    invalidatePendingAccessToken();
    qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

    // Restore OAuth2 authorization if have it for this domain.
    if (_knownAuths.contains(domainURL)) {
        _currentAuth = _knownAuths.value(domainURL);
    } else {
        _currentAuth = DomainAccountDetails();
        _currentAuth.domainURL = domainURL;
    }

    emit hasLogInChanged(hasLogIn());
}

void DomainAccountManager::setAuthURL(const QUrl& authURL) {
    if (authURL == _currentAuth.authURL) {
        return;
    }

    invalidatePendingAccessToken();
    _currentAuth.authURL = authURL;
    qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

    _currentAuth.accessToken = "";
    _currentAuth.refreshToken = "";

    emit hasLogInChanged(hasLogIn());
}

bool DomainAccountManager::hasLogIn() {
    return !_currentAuth.authURL.isEmpty();
}

bool DomainAccountManager::isLoggedIn() {
    return !_currentAuth.authURL.isEmpty() && hasValidAccessToken();
}

overte::network::RequestTicket DomainAccountManager::requestAccessToken(const QString& username, const QString& password) {

    invalidatePendingAccessToken();
    const auto ticket = _accessTokenRequests.snapshot();
    if (!ticket.current()) {
        emit loginFailed();
        emit loginRequestFinished(ticket, _accessTokenRequests.snapshot(), static_cast<int>(LoginOutcome::Failed));
        return ticket;
    }

    _currentAuth.username = username;
    _currentAuth.accessToken = "";
    _currentAuth.refreshToken = "";

    QNetworkRequest request;

    request.setHeader(QNetworkRequest::UserAgentHeader, NetworkingConstants::OVERTE_USER_AGENT);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/x-www-form-urlencoded");

    // miniOrange WordPress API Authentication plugin:
    // - Requires "client_id" parameter.
    // - Ignores "state" parameter.
    QByteArray formData;
    formData.append("grant_type=password&");
    formData.append("username=" + QUrl::toPercentEncoding(username) + "&");
    formData.append("password=" + QUrl::toPercentEncoding(password) + "&");
    formData.append("client_id=" + QUrl::toPercentEncoding(_currentAuth.clientID));

    request.setUrl(_currentAuth.authURL);

    // Never replay a credential-bearing POST to an unreviewed redirect target.
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);

    QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();
    QNetworkReply* requestReply = networkAccessManager.post(request, formData);
    _pendingAccessTokenReply = requestReply;
    overte::network::watchRequest(requestReply, ticket);
    requestReply->setReadBufferSize(MAX_DOMAIN_AUTH_RESPONSE_BYTES + 1);
    connect(requestReply, &QNetworkReply::readyRead, this, [this, requestReply, ticket] {
        if (requestReply == _pendingAccessTokenReply && ticket.current() &&
                requestReply->bytesAvailable() > MAX_DOMAIN_AUTH_RESPONSE_BYTES) {
            invalidatePendingAccessToken(LoginOutcome::ResponseRejected);
            emit loginFailed();
        }
    });
    connect(requestReply, &QNetworkReply::finished, this, &DomainAccountManager::requestAccessTokenFinished);
    connect(requestReply, &QNetworkReply::finished, requestReply, &QObject::deleteLater);
    auto deadline = new QTimer(requestReply);
    deadline->setSingleShot(true);
    deadline->setInterval(15000);
    connect(requestReply, &QNetworkReply::finished, deadline, &QTimer::stop);
    connect(deadline, &QTimer::timeout, this, [this, requestReply, ticket] {
        if (requestReply != _pendingAccessTokenReply || !ticket.current()) {
            return;
        }
        invalidatePendingAccessToken(LoginOutcome::TimedOut);
        emit loginFailed();
    });
    deadline->start();
    return ticket;
}

void DomainAccountManager::requestAccessTokenFinished() {

    auto* requestReply = qobject_cast<QNetworkReply*>(sender());
    if (!requestReply || requestReply != _pendingAccessTokenReply || !overte::network::replyCurrent(requestReply)) {
        return;
    }
    _pendingAccessTokenReply.clear(); // One terminal reply; reject duplicates.
    const auto ticket = requestReply->property("_overte_request_ticket").value<overte::network::RequestTicket>();

    auto httpStatus = requestReply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    const auto payload = requestReply->read(MAX_DOMAIN_AUTH_RESPONSE_BYTES + 1);
    QJsonParseError parseError;
    const auto jsonResponse = QJsonDocument::fromJson(payload, &parseError);
    const auto rootObject = jsonResponse.object();
    const auto accessToken = rootObject.value("access_token");
    const auto refreshToken = rootObject.value("refresh_token");
    const bool validResponse = requestReply->error() == QNetworkReply::NoError &&
        payload.size() <= MAX_DOMAIN_AUTH_RESPONSE_BYTES && requestReply->bytesAvailable() == 0 &&
        parseError.error == QJsonParseError::NoError && jsonResponse.isObject() &&
        accessToken.isString() && !accessToken.toString().trimmed().isEmpty() &&
        (refreshToken.isUndefined() || refreshToken.isString());
    if (200 <= httpStatus && httpStatus < 300 && validResponse) {

        // miniOrange plugin provides no scope.
        if (rootObject.contains("access_token")) {
            // Success.
            auto nodeList = DependencyManager::get<NodeList>();
            _currentAuth.authedDomainName = nodeList->getDomainHandler().getHostname();
            QUrl rootURL = requestReply->url();
            rootURL.setPath("");
            setTokensFromJSON(rootObject, rootURL);

            // Remember domain login for the current Interface session.
            _knownAuths.insert(_currentAuth.domainURL, _currentAuth);

            // ####### TODO: Handle "keep me logged in".

            emit loginComplete();
            emit loginRequestFinished(ticket, ticket, static_cast<int>(LoginOutcome::Succeeded));
        } else {
            // Failure.
            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::AuthFailed);
            emit loginFailed();
            emit loginRequestFinished(ticket, ticket, static_cast<int>(LoginOutcome::Failed));
        }

    } else {
        // Failure.
        qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::AuthFailed);
        emit loginFailed();
        emit loginRequestFinished(ticket, ticket, static_cast<int>(LoginOutcome::Failed));
    }
}

void DomainAccountManager::sendInterfaceAccessTokenToServer() {
    emit newTokens();
}

bool DomainAccountManager::accessTokenIsExpired() {
    // ####### TODO: accessTokenIsExpired()
    return true;
}


bool DomainAccountManager::hasValidAccessToken() {
    // ###### TODO: wire this up to actually retrieve a token (based on session or storage) and confirm that it is in fact valid and relevant to the current domain.
    // QString currentDomainAccessToken = domainAccessToken.get();
    QString currentDomainAccessToken = _currentAuth.accessToken;

    // if (currentDomainAccessToken.isEmpty() || accessTokenIsExpired()) {
    if (currentDomainAccessToken.isEmpty()) {
        if (VERBOSE_HTTP_REQUEST_DEBUGGING) {
            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::AuthRequired);
        }

        return false;
    }

    // ####### TODO

    // if (!_isWaitingForTokenRefresh && needsToRefreshToken()) {
    //     refreshAccessToken();
    // }

    return true;
}

void DomainAccountManager::setTokensFromJSON(const QJsonObject& jsonObject, const QUrl& url) {
    _currentAuth.accessToken = jsonObject["access_token"].toString();
    _currentAuth.refreshToken = jsonObject["refresh_token"].toString();
}

bool DomainAccountManager::checkAndSignalForAccessToken() {
    bool hasToken = hasValidAccessToken();

    // ####### TODO: Handle hasToken == true.
    // It causes the login dialog not to display (OK) but somewhere the domain server needs to be sent it (and if domain server
    // gets error when trying to use it then user should be prompted to login).
    hasToken = false;

    if (!hasToken) {
        // Emit a signal so somebody can call back to us and request an access token given a user name and password.

        // Dialog can be hidden immediately after showing if we've just teleported to the domain, unless the signal is delayed.
        auto domain = _currentAuth.authURL.host();
        const auto ticket = _accessTokenRequests.snapshot();
        QTimer::singleShot(500, this, [this, domain, ticket] {
            if (!ticket.current()) {
                return;
            }
            emit this->authRequired(domain);
        });
    }

    return hasToken;
}
