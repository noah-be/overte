//
//  OAuthAccessToken.h
//  libraries/networking/src
//
//  Created by Stephen Birarda on 2/18/2014.
//  Copyright 2014 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#ifndef hifi_OAuthAccessToken_h
#define hifi_OAuthAccessToken_h

#include <QtCore/QObject>
#include <QtCore/QDateTime>
#include <QtCore/QJsonObject>
#include "OAuthTokenValidation.h"

class OAuthAccessToken : public QObject {
    Q_OBJECT
public:
    OAuthAccessToken();
    OAuthAccessToken(const QJsonObject& jsonObject);
    OAuthAccessToken(const OAuthAccessToken& otherToken);
    OAuthAccessToken& operator=(const OAuthAccessToken& otherToken);
    
    QByteArray authorizationHeaderValue() const {
        return isExpired() ? QByteArray() : QString("Bearer %1").arg(token).toUtf8();
    }
     
    bool isExpired() const {
        // Preserve the existing explicit raw-token API's no-expiry sentinel.
        // JSON responses always require a positive lifetime and Bearer type.
        return !overte::network::validBearerCredential(token) ||
            (tokenType.isEmpty() ? expiryTimestamp != -1 :
                tokenType.compare(QStringLiteral("Bearer"), Qt::CaseInsensitive) != 0) ||
            (expiryTimestamp != -1 && expiryTimestamp <= QDateTime::currentMSecsSinceEpoch());
    }
    
    QString token;
    QString refreshToken;
    qlonglong expiryTimestamp;
    QString tokenType;
    
    friend QDataStream& operator<<(QDataStream &out, const OAuthAccessToken& token);
    friend QDataStream& operator>>(QDataStream &in, OAuthAccessToken& token);
private:
    void swap(OAuthAccessToken& otherToken);
};

#endif // hifi_OAuthAccessToken_h
