//
//  DomainAccountManager.h
//  libraries/networking/src
//
//  Created by David Rowe on 23 Jul 2020.
//  Copyright 2020 Vircadia contributors.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#ifndef hifi_DomainAccountManager_h
#define hifi_DomainAccountManager_h

#include <QtCore/QObject>
#include <QtCore/QUrl>
#include <QtCore/QPointer>
#include <QtCore/QDeadlineTimer>
#include "RequestCancellation.h"

#include <DependencyManager.h>


struct DomainAccountDetails {
    QUrl domainURL;
    QUrl authURL;
    QString clientID;
    QString username;
    QString accessToken;
    QString refreshToken;
    QString authedDomainName;
    // A missing server lifetime retains the existing session-only semantics.
    // A supplied lifetime uses a monotonic deadline, copied with cached auth.
    QDeadlineTimer accessTokenDeadline { QDeadlineTimer::Forever };
};


class DomainAccountManager : public QObject, public Dependency {
    Q_OBJECT
public:
    enum class LoginOutcome { Succeeded, Failed, Cancelled, TimedOut, ResponseRejected };
    Q_ENUM(LoginOutcome)
    DomainAccountManager();
    ~DomainAccountManager() override;

    void setDomainURL(const QUrl& domainURL);
    void setAuthURL(const QUrl& authURL);
    void setClientID(const QString& clientID);
    void setClientAuthVisibility(bool foreground);

    const QString& getUsername() { return _currentAuth.username; }
    const QString& getAccessToken();
    const QString& getRefreshToken() { return _currentAuth.refreshToken; }
    const QString& getAuthedDomainName() { return _currentAuth.authedDomainName; }

    bool hasLogIn();
    bool isLoggedIn();
    bool isAccessTokenRequestPending() const { return !_pendingAccessTokenReply.isNull(); }
    overte::network::RequestTicket accessTokenRequestTicket() const {
        return isAccessTokenRequestPending() ? _accessTokenRequests.snapshot() : overte::network::RequestTicket();
    }

    Q_INVOKABLE bool checkAndSignalForAccessToken();

public slots:
    overte::network::RequestTicket requestAccessToken(const QString& username, const QString& password);
    void requestAccessTokenFinished();

signals:
    void hasLogInChanged(bool hasLogIn);
    void authRequired(const QString& domain);
    void loginComplete();
    void loginFailed();
    void loginRequestFinished(overte::network::RequestTicket ticket,
                              overte::network::RequestTicket context, int outcome);
    void logoutComplete();
    void newTokens();

private:
    overte::network::RequestTicket invalidatePendingAccessToken(LoginOutcome outcome = LoginOutcome::Cancelled, bool suspend = false);
    bool hasValidAccessToken();
    bool accessTokenIsExpired();
    void setTokensFromJSON(const QJsonObject&, const QUrl& url);
    void sendInterfaceAccessTokenToServer();

    DomainAccountDetails _currentAuth;
    QHash<QUrl, DomainAccountDetails> _knownAuths;  // <domainURL, DomainAccountDetails>
    overte::network::RequestScope _accessTokenRequests;
    QPointer<QNetworkReply> _pendingAccessTokenReply;
};

#endif  // hifi_DomainAccountManager_h
