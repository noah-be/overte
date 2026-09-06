//
//  AccountManager.cpp
//  libraries/networking/src
//
//  Created by Stephen Birarda on 2/18/2014.
//  Copyright 2014 High Fidelity, Inc.
//  Copyright 2023-2024 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "AccountManager.h"

#include <memory>

#include <QtCore/QDataStream>
#include <QtCore/QDir>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include "../../../security/redaction/SafeDiagnostics.h"
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QMap>
#include <QtCore/QStringList>
#include <QtCore/QStandardPaths>
#include <QtCore/QUrlQuery>
#include <QtCore/QThreadPool>
#include <QtNetwork/QHttpMultiPart>
#include <QtNetwork/QNetworkRequest>
#include <QtNetwork/QNetworkReply>
#include <qthread.h>

#include <SettingHandle.h>

#include "NetworkLogging.h"
#include "NodeList.h"
#include "udt/PacketHeaders.h"
#include "RSAKeypairGenerator.h"
#include "SharedUtil.h"
#include "UserActivityLogger.h"


const bool VERBOSE_HTTP_REQUEST_DEBUGGING = false;

Q_DECLARE_METATYPE(OAuthAccessToken)
Q_DECLARE_METATYPE(DataServerAccountInfo)
Q_DECLARE_METATYPE(QNetworkAccessManager::Operation)
Q_DECLARE_METATYPE(JSONCallbackParameters)

const QString ACCOUNTS_GROUP = "accounts";

const int POST_SETTINGS_INTERVAL = 10 * MSECS_PER_SECOND;
const int PULL_SETTINGS_RETRY_INTERVAL = 2 * MSECS_PER_SECOND;
const int MAX_PULL_RETRIES = 10;

JSONCallbackParameters::JSONCallbackParameters(QObject* callbackReceiver,
    const QString& jsonCallbackMethod,
    const QString& errorCallbackMethod,
    const QJsonObject& callbackData) :
    callbackReceiver(callbackReceiver),
    jsonCallbackMethod(jsonCallbackMethod),
    errorCallbackMethod(errorCallbackMethod),
    callbackData(callbackData)
{

}

QJsonObject AccountManager::dataObjectFromResponse(QNetworkReply* requestReply) {
    QJsonObject jsonObject = QJsonDocument::fromJson(requestReply->readAll()).object();

    static const QString STATUS_KEY = "status";
    static const QString DATA_KEY = "data";

    if (jsonObject.contains(STATUS_KEY) && jsonObject[STATUS_KEY] == "success" && jsonObject.contains(DATA_KEY)) {
        return jsonObject[DATA_KEY].toObject();
    } else {
        return QJsonObject();
    }
}

AccountManager::AccountManager(bool accountSettingsEnabled, UserAgentGetter userAgentGetter) :
    _userAgentGetter(userAgentGetter),
    _authURL(),
    _accountSettingsEnabled(accountSettingsEnabled)
{
    qRegisterMetaType<OAuthAccessToken>("OAuthAccessToken");
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
    qRegisterMetaTypeStreamOperators<OAuthAccessToken>("OAuthAccessToken");
#endif

    qRegisterMetaType<DataServerAccountInfo>("DataServerAccountInfo");
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
    qRegisterMetaTypeStreamOperators<DataServerAccountInfo>("DataServerAccountInfo");
#endif

    qRegisterMetaType<QNetworkAccessManager::Operation>("QNetworkAccessManager::Operation");
    qRegisterMetaType<JSONCallbackParameters>("JSONCallbackParameters");

    qRegisterMetaType<QHttpMultiPart*>("QHttpMultiPart*");

    qRegisterMetaType<AccountManagerAuth::Type>();
    connect(this, &AccountManager::loginComplete, this, &AccountManager::uploadPublicKey);
    connect(this, &AccountManager::loginComplete, this, &AccountManager::requestAccountSettings);

    _pullSettingsRetryTimer = new QTimer(this);
    _pullSettingsRetryTimer->setSingleShot(true);
    _pullSettingsRetryTimer->setInterval(PULL_SETTINGS_RETRY_INTERVAL);
    connect(_pullSettingsRetryTimer, &QTimer::timeout, this, &AccountManager::requestAccountSettings);

    _postSettingsTimer = new QTimer(this);
    _postSettingsTimer->setInterval(POST_SETTINGS_INTERVAL);
    connect(this, SIGNAL(accountSettingsLoaded()), _postSettingsTimer, SLOT(start()));
    connect(this, &AccountManager::logoutComplete, _postSettingsTimer, &QTimer::stop);
    connect(_postSettingsTimer, &QTimer::timeout, this, &AccountManager::postAccountSettings);
    connect(qApp, &QCoreApplication::aboutToQuit, this, &AccountManager::postAccountSettings);
}

const QString ACCOUNT_MANAGER_REQUESTED_SCOPE = "owner";

void AccountManager::logout() {
    postAccountSettings();
    _numPullRetries = 0;

    // a logout means we want to delete the DataServerAccountInfo we currently have for this URL, in-memory and in file
    _accountInfo = DataServerAccountInfo();

    // remove this account from the account settings file
    removeAccountFromFile();
    saveLoginStatus(false);

    emit logoutComplete();
    // the username has changed to blank
    emit usernameChanged(QString());

    _settings.loggedOut();
}

QString accountFileDir() {
#if defined(Q_OS_ANDROID)
    return QStandardPaths::writableLocation(QStandardPaths::CacheLocation) + "/../files";
#else
    return QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);
#endif
}

QString accountFilePath() {
    return accountFileDir() + "/AccountInfo.bin";
}

namespace {
overte::security::AccountStoreCoordinator& protectedAccountCoordinator() {
    static overte::security::AccountStoreCoordinator coordinator;
    return coordinator;
}

overte::security::LegacyAccountInput legacyAccountInput() {
    using namespace overte::security;
    return {
        [](AccountBytes& output) {
            QFileInfo info(accountFilePath());
            if (info.isSymLink()) { return StoreResult::Corrupt; }
            if (!info.exists()) { return StoreResult::Absent; }
            if (!info.isFile() || info.size() <= 0 || info.size() > static_cast<qint64>(MAX_ACCOUNT_BYTES)) {
                return StoreResult::Corrupt;
            }
            QFile input(accountFilePath());
            if (!input.open(QIODevice::ReadOnly)) { return StoreResult::IoError; }
            QByteArray bytes = input.read(MAX_ACCOUNT_BYTES + 1);
            if (bytes.isEmpty() || bytes.size() > static_cast<int>(MAX_ACCOUNT_BYTES) || !input.atEnd()) {
                bytes.fill('\0');
                return StoreResult::Corrupt;
            }
            QDataStream stream(bytes);
            QVariantMap checked;
            stream >> checked;
            const bool valid = stream.status() == QDataStream::Ok && stream.atEnd();
            if (valid) { output.assign(bytes.begin(), bytes.end()); }
            bytes.fill('\0');
            return valid ? StoreResult::Ok : StoreResult::Corrupt;
        },
        []() {
            QFileInfo info(accountFilePath());
            if (info.isSymLink()) { return false; }
            return !info.exists() || QFile::remove(accountFilePath());
        }
    };
}
}

bool AccountManager::installProtectedAccountStore(std::shared_ptr<overte::security::ProtectedAccountStore> adapter) {
    return protectedAccountCoordinator().install(std::move(adapter));
}

QVariantMap accountMapFromFile(bool& success) {
    overte::security::AccountBytes bytes;
    auto result = protectedAccountCoordinator().read(bytes, legacyAccountInput());
    success = result == overte::security::StoreResult::Absent;
    QVariantMap accountMap;
    if (result == overte::security::StoreResult::Ok) {
        QByteArray serialized(reinterpret_cast<const char*>(bytes.data()), static_cast<int>(bytes.size()));
        QDataStream stream(serialized);
        stream >> accountMap;
        success = stream.status() == QDataStream::Ok && stream.atEnd();
        serialized.fill('\0');
    }
    overte::security::clearAccountBytes(bytes);
    return success ? accountMap : QVariantMap();
}

void AccountManager::setAuthURL(const QUrl& authURL) {
    if (_authURL != authURL) {
        _authURL = authURL;

        qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

        // check if there are existing access tokens to load from settings
        bool loadedMap = false;
        auto accountsMap = accountMapFromFile(loadedMap);

        _accountInfo = DataServerAccountInfo();
        if (loadedMap) {
            // pull out the stored account info and store it in memory
            _accountInfo = accountsMap[_authURL.toString()].value<DataServerAccountInfo>();

            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
        } else {
            qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
            emit authRequired();
        }

        if (_isAgent && !_accountInfo.getAccessToken().token.isEmpty() && !_accountInfo.hasProfile()) {
            // we are missing profile information, request it now
            requestProfile();
        }

        // prepare to refresh our token if it is about to expire
        if (needsToRefreshToken()) {
            refreshAccessToken();
        }

        if (isLoggedIn()) {
            emit loginComplete(_authURL);
        }

        // tell listeners that the auth endpoint has changed
        emit authEndpointChanged();
    }
}

void AccountManager::updateAuthURLFromMetaverseServerURL() {
    setAuthURL(MetaverseAPI::getCurrentMetaverseServerURL());
}

void AccountManager::setSessionID(const QUuid& sessionID) {
    if (_sessionID != sessionID) {
        qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
        _sessionID = sessionID;
    }
}

QNetworkRequest AccountManager::createRequest(QString path, AccountManagerAuth::Type authType) {
    QNetworkRequest networkRequest;
    networkRequest.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::NoLessSafeRedirectPolicy);
    networkRequest.setHeader(QNetworkRequest::UserAgentHeader, _userAgentGetter());

    networkRequest.setRawHeader(METAVERSE_SESSION_ID_HEADER,
                                uuidStringWithoutCurlyBraces(_sessionID).toLocal8Bit());

    QUrl requestURL = _authURL;
    if (requestURL.isEmpty()) {  // Assignment client doesn't set _authURL.
        requestURL = getMetaverseServerURL();
    }

    // qCDebug(networking) << "Received path" << path;
    // qCDebug(networking) << "path.left(path.indexOf(\" ? \"))" << path.left(path.indexOf("?"));
    // qCDebug(networking) << "getMetaverseServerURLPath(true)" << getMetaverseServerURLPath(true);

    int queryStringLocation = path.indexOf("?");
    if (path.startsWith("/")) {
        requestURL.setPath(getMetaverseServerURLPath(false) + path.left(queryStringLocation));
    } else {
        requestURL.setPath(getMetaverseServerURLPath(true) + path.left(queryStringLocation));
    }

    // qCDebug(networking) << "Creating request path" << requestURL;
    // qCDebug(networking) << "requestURL.isValid()" << requestURL.isValid();
    // qCDebug(networking) << "requestURL.errorString()" << requestURL.errorString();

    if (queryStringLocation >= 0) {
        QUrlQuery query(path.mid(queryStringLocation+1));
        requestURL.setQuery(query);
    }

    if (authType != AccountManagerAuth::None ) {
        if (hasValidAccessToken()) {
            networkRequest.setRawHeader(ACCESS_TOKEN_AUTHORIZATION_HEADER,
                                        _accountInfo.getAccessToken().authorizationHeaderValue());
        } else {
            if (authType == AccountManagerAuth::Required) {
                qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
                return QNetworkRequest();
            }
        }
    }

    networkRequest.setUrl(requestURL);

    return networkRequest;
}

void AccountManager::sendRequest(const QString& path,
                                 AccountManagerAuth::Type authType,
                                 QNetworkAccessManager::Operation operation,
                                 const JSONCallbackParameters& callbackParams,
                                 const QByteArray& dataByteArray,
                                 QHttpMultiPart* dataMultiPart,
                                 const QVariantMap& propertyMap) {

    if (thread() != QThread::currentThread()) {
        QMetaObject::invokeMethod(this, "sendRequest",
                                  Q_ARG(const QString&, path),
                                  Q_ARG(AccountManagerAuth::Type, authType),
                                  Q_ARG(QNetworkAccessManager::Operation, operation),
                                  Q_ARG(const JSONCallbackParameters&, callbackParams),
                                  Q_ARG(const QByteArray&, dataByteArray),
                                  Q_ARG(QHttpMultiPart*, dataMultiPart),
                                  Q_ARG(QVariantMap, propertyMap));
        return;
    }

    if (!callbackParams.requestTicket.current()) { return; }
    QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();

    QNetworkRequest networkRequest = createRequest(path, authType);

    if (VERBOSE_HTTP_REQUEST_DEBUGGING) {
        qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

        if (!dataByteArray.isEmpty()) {
            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
        }
    }

    QNetworkReply* networkReply = NULL;

    switch (operation) {
        case QNetworkAccessManager::GetOperation:
            networkReply = networkAccessManager.get(networkRequest);
            break;
        case QNetworkAccessManager::PostOperation:
        case QNetworkAccessManager::PutOperation:
            if (dataMultiPart) {
                if (operation == QNetworkAccessManager::PostOperation) {
                    networkReply = networkAccessManager.post(networkRequest, dataMultiPart);
                } else {
                    networkReply = networkAccessManager.put(networkRequest, dataMultiPart);
                }

                // make sure dataMultiPart is destroyed when the reply is
                connect(networkReply, &QNetworkReply::destroyed, dataMultiPart, &QHttpMultiPart::deleteLater);
            } else {
                networkRequest.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
                if (operation == QNetworkAccessManager::PostOperation) {
                    networkReply = networkAccessManager.post(networkRequest, dataByteArray);
                } else {
                    networkReply = networkAccessManager.put(networkRequest, dataByteArray);
                }
            }

            break;
        case QNetworkAccessManager::DeleteOperation:
            networkReply = networkAccessManager.sendCustomRequest(networkRequest, "DELETE");
            break;
        default:
            // other methods not yet handled
            break;
    }

    if (networkReply) {
        if (!propertyMap.isEmpty()) {
            // we have properties to set on the reply so the user can check them after
            foreach(const QString& propertyKey, propertyMap.keys()) {
                networkReply->setProperty(qPrintable(propertyKey), propertyMap.value(propertyKey));
            }
        }

        overte::network::watchRequest(networkReply, callbackParams.requestTicket);
        if (callbackParams.requestTicket.scoped() && callbackParams.callbackReceiver) {
            connect(callbackParams.callbackReceiver, &QObject::destroyed, networkReply, [networkReply, callbackParams] {
                // QObject::destroyed is emitted before all receiver connections
                // disappear. Invalidate BEFORE abort synchronously emits finished.
                callbackParams.requestTicket.deactivateIfCurrent();
                networkReply->abort();
                networkReply->deleteLater();
            });
        }
        connect(networkReply, &QNetworkReply::finished, this, [this, networkReply, callbackParams] {
            if (!callbackParams.requestTicket.current()) { return; }
            // double check if the finished network reply had a session ID in the header and make
            // sure that our session ID matches that value if so
            if (networkReply->hasRawHeader(METAVERSE_SESSION_ID_HEADER)) {
                _sessionID = QUuid::fromString(QString::fromLatin1(
                    networkReply->rawHeader(METAVERSE_SESSION_ID_HEADER)));
            }
        });


        if (callbackParams.isEmpty()) {
            connect(networkReply, &QNetworkReply::finished, networkReply, &QNetworkReply::deleteLater);
        } else {
            // There's a cleaner way to fire the JSON/error callbacks below and ensure that deleteLater is called for the
            // request reply - unfortunately it requires Qt 5.10 which the Android build does not support as of 06/26/18

            connect(networkReply, &QNetworkReply::finished, callbackParams.callbackReceiver,
                    [callbackParams, networkReply] {
                if (!callbackParams.requestTicket.current()) {
                    networkReply->deleteLater();
                    return;
                }
                if (networkReply->error() == QNetworkReply::NoError) {
                    if (!callbackParams.jsonCallbackMethod.isEmpty()) {
                        bool invoked = false;
                        if (callbackParams.callbackData.isEmpty()) {
                            invoked = QMetaObject::invokeMethod(callbackParams.callbackReceiver,
                                qPrintable(callbackParams.jsonCallbackMethod),
                                Q_ARG(QNetworkReply*, networkReply));
                        } else {
                            invoked = QMetaObject::invokeMethod(callbackParams.callbackReceiver,
                                qPrintable(callbackParams.jsonCallbackMethod),
                                Q_ARG(QNetworkReply*, networkReply),
                                Q_ARG(QJsonObject, callbackParams.callbackData));
                        }

                        if (!invoked) {
                            QString error = "Could not invoke " + callbackParams.jsonCallbackMethod + " with QNetworkReply* "
                            + "on callbackReceiver.";
                            qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
                            Q_ASSERT_X(invoked, "AccountManager::passErrorToCallback", qPrintable(error));
                        }
                    } else {
                        if (VERBOSE_HTTP_REQUEST_DEBUGGING) {
                            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
                            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
                        }
                    }
                } else {
                    if (!callbackParams.errorCallbackMethod.isEmpty()) {
                        bool invoked = false;
                        if (callbackParams.callbackData.isEmpty()) {
                            invoked = QMetaObject::invokeMethod(callbackParams.callbackReceiver,
                                qPrintable(callbackParams.errorCallbackMethod),
                                Q_ARG(QNetworkReply*, networkReply));
                        }
                        else {
                            invoked = QMetaObject::invokeMethod(callbackParams.callbackReceiver,
                                qPrintable(callbackParams.errorCallbackMethod),
                                Q_ARG(QNetworkReply*, networkReply),
                                Q_ARG(QJsonObject, callbackParams.callbackData));
                        }

                        if (!invoked) {
                            QString error = "Could not invoke " + callbackParams.errorCallbackMethod + " with QNetworkReply* "
                            + "on callbackReceiver.";
                            qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
                            Q_ASSERT_X(invoked, "AccountManager::passErrorToCallback", qPrintable(error));
                        }

                    } else {
                        if (VERBOSE_HTTP_REQUEST_DEBUGGING) {
                            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
                            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
                            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
                        }
                    }
                }

                networkReply->deleteLater();
            });
        }
    }
}

bool writeAccountMapToFile(const QVariantMap& accountMap) {
    QByteArray serialized;
    QDataStream stream(&serialized, QIODevice::WriteOnly);
    stream << accountMap;
    if (stream.status() != QDataStream::Ok || serialized.size() > static_cast<int>(overte::security::MAX_ACCOUNT_BYTES)) {
        serialized.fill('\0');
        return false;
    }
    overte::security::AccountBytes bytes(serialized.begin(), serialized.end());
    serialized.fill('\0');
    auto result = protectedAccountCoordinator().write(bytes, legacyAccountInput());
    overte::security::clearAccountBytes(bytes);
    return result == overte::security::StoreResult::Ok;
}

void AccountManager::persistAccountToFile() {

    qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

    bool wasLoaded = false;
    auto accountMap = accountMapFromFile(wasLoaded);

    if (wasLoaded) {
        // replace the current account information for this auth URL in the account map
        accountMap[_authURL.toString()] = QVariant::fromValue(_accountInfo);

        // re-open the file and truncate it
        if (writeAccountMapToFile(accountMap)) {
            return;
        }
    }

    qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
    _accountInfo = DataServerAccountInfo();
    emit authRequired();
}

void AccountManager::removeAccountFromFile() {
    _accountInfo = DataServerAccountInfo();
    _pendingPrivateKey.fill('\0');
    _pendingPrivateKey.clear();
    // The adapter stores one account map. Logout erases the complete map so an
    // unreadable/corrupt map cannot retain an account silently.
    if (protectedAccountCoordinator().erase(legacyAccountInput()) != overte::security::StoreResult::Ok) {
        qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
    }
}

void AccountManager::setAccountInfo(const DataServerAccountInfo &newAccountInfo) {
    _accountInfo = newAccountInfo;
    _pendingPrivateKey.clear();
    if (_isAgent && !_accountInfo.getAccessToken().token.isEmpty() && !_accountInfo.hasProfile()) {
        // we are missing profile information, request it now
        requestProfile();
    }

    // prepare to refresh our token if it is about to expire
    if (needsToRefreshToken()) {
        refreshAccessToken();
    }
}

bool AccountManager::hasValidAccessToken() {

    if (_accountInfo.getAccessToken().token.isEmpty() || _accountInfo.getAccessToken().isExpired()) {

        if (VERBOSE_HTTP_REQUEST_DEBUGGING) {
            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
        }

        return false;
    } else {

        if (!_isWaitingForTokenRefresh && needsToRefreshToken()) {
            refreshAccessToken();
        }

        return true;
    }
}

bool AccountManager::checkAndSignalForAccessToken() {
    bool hasToken = hasValidAccessToken();

    if (!hasToken) {
        // emit a signal so somebody can call back to us and request an access token given a username and password

        // Dialog can be hidden immediately after showing if we've just teleported to the domain, unless the signal is delayed.
        QTimer::singleShot(500, this, [this] { emit this->authRequired(); });
    }

    return hasToken;
}

bool AccountManager::needsToRefreshToken() {
    if (!_accountInfo.getAccessToken().token.isEmpty() && _accountInfo.getAccessToken().expiryTimestamp > 0) {
        static constexpr int MIN_REMAINING_MS = 1 * SECS_PER_HOUR * MSECS_PER_SECOND;  // 1 h
        auto expireThreshold = QDateTime::currentDateTimeUtc().addMSecs(MIN_REMAINING_MS).toMSecsSinceEpoch();
        return _accountInfo.getAccessToken().expiryTimestamp < expireThreshold;
    } else {
        return false;
    }
}

void AccountManager::setAccessTokenForCurrentAuthURL(const QString& accessToken) {
    // replace the account info access token with a new OAuthAccessToken
    OAuthAccessToken newOAuthToken;
    newOAuthToken.token = accessToken;

    if (!accessToken.isEmpty()) {
        qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::AuthReady);
    } else if (!_accountInfo.getAccessToken().token.isEmpty()) {
        qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
    }

    _accountInfo.setAccessToken(newOAuthToken);

    persistAccountToFile();
}

void AccountManager::setTemporaryDomain(const QUuid& domainID, const QString& key) {
    _accountInfo.setTemporaryDomain(domainID, key);
    persistAccountToFile();
}

void AccountManager::requestAccessToken(const QString& login, const QString& password) {

    QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();

    QNetworkRequest request;
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::NoLessSafeRedirectPolicy);
    request.setHeader(QNetworkRequest::UserAgentHeader, _userAgentGetter());

    QUrl grantURL = _authURL;
    grantURL.setPath(getMetaverseServerURLPath() + "/oauth/token");

    QByteArray postData;
    postData.append("grant_type=password&");
    postData.append("username=" + QUrl::toPercentEncoding(login) + "&");
    postData.append("password=" + QUrl::toPercentEncoding(password) + "&");
    postData.append("scope=" + ACCOUNT_MANAGER_REQUESTED_SCOPE.toUtf8());

    request.setUrl(grantURL);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/x-www-form-urlencoded");

    QNetworkReply* requestReply = networkAccessManager.post(request, postData);
    connect(requestReply, &QNetworkReply::finished, this, &AccountManager::requestAccessTokenFinished);
}

void AccountManager::requestAccessTokenWithAuthCode(const QString& authCode, const QString& clientId, const QString& clientSecret, const QString& redirectUri) {
    QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();

    QNetworkRequest request;
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::NoLessSafeRedirectPolicy);
    request.setHeader(QNetworkRequest::UserAgentHeader, _userAgentGetter());

    QUrl grantURL = _authURL;
    grantURL.setPath(getMetaverseServerURLPath() + "/oauth/token");

    QByteArray postData;
    postData.append("grant_type=authorization_code&");
    postData.append("client_id=" + clientId.toUtf8() + "&");
    postData.append("client_secret=" + clientSecret.toUtf8() + "&");
    postData.append("code=" + authCode.toUtf8() + "&");
    postData.append("redirect_uri=" + QUrl::toPercentEncoding(redirectUri));

    request.setUrl(grantURL);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/x-www-form-urlencoded");

    QNetworkReply* requestReply = networkAccessManager.post(request, postData);
    connect(requestReply, &QNetworkReply::finished, this, &AccountManager::requestAccessTokenFinished);
}

void AccountManager::requestAccessTokenWithSteam(QByteArray authSessionTicket) {
    QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();

    QNetworkRequest request;
    request.setHeader(QNetworkRequest::UserAgentHeader, _userAgentGetter());

    QUrl grantURL = _authURL;
    grantURL.setPath(getMetaverseServerURLPath() + "/oauth/token");

    QByteArray postData;
    postData.append("grant_type=password&");
    postData.append("steam_auth_ticket=" + QUrl::toPercentEncoding(authSessionTicket) + "&");
    postData.append("scope=" + ACCOUNT_MANAGER_REQUESTED_SCOPE.toUtf8());

    request.setUrl(grantURL);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/x-www-form-urlencoded");

    QNetworkReply* requestReply = networkAccessManager.post(request, postData);
    connect(requestReply, &QNetworkReply::finished, this, &AccountManager::requestAccessTokenFinished);
#if QT_VERSION >= QT_VERSION_CHECK(5, 15, 0)
    connect(requestReply, &QNetworkReply::errorOccurred, this, &AccountManager::requestAccessTokenError);
#else
    connect(requestReply, SIGNAL(error(QNetworkReply::NetworkError)), this, SLOT(requestAccessTokenError(QNetworkReply::NetworkError)));
#endif
}

void AccountManager::requestAccessTokenWithOculus(const QString& nonce, const QString &oculusID) {
    QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();

    QNetworkRequest request;
    request.setHeader(QNetworkRequest::UserAgentHeader, _userAgentGetter());

    QUrl grantURL = _authURL;
    grantURL.setPath(getMetaverseServerURLPath() + "/oauth/token");

    QByteArray postData;
    postData.append("grant_type=password&");
    postData.append("oculus_nonce=" + nonce.toUtf8() + "&");
    postData.append("oculus_id=" + oculusID.toUtf8() + "&");
    postData.append("scope=" + ACCOUNT_MANAGER_REQUESTED_SCOPE.toUtf8());

    request.setUrl(grantURL);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/x-www-form-urlencoded");

    QNetworkReply* requestReply = networkAccessManager.post(request, postData);
    connect(requestReply, &QNetworkReply::finished, this, &AccountManager::requestAccessTokenFinished);
#if QT_VERSION >= QT_VERSION_CHECK(5, 15, 0)
    connect(requestReply, &QNetworkReply::errorOccurred, this, &AccountManager::requestAccessTokenError);
#else
    connect(requestReply, SIGNAL(error(QNetworkReply::NetworkError)), this, SLOT(requestAccessTokenError(QNetworkReply::NetworkError)));
#endif
}

void AccountManager::refreshAccessToken() {

    // we can't refresh our access token if we don't have a refresh token, so check for that first
    if (!_accountInfo.getAccessToken().refreshToken.isEmpty()) {
        qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

        _isWaitingForTokenRefresh = true;

        QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();

        QNetworkRequest request;
        request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::NoLessSafeRedirectPolicy);
        request.setHeader(QNetworkRequest::UserAgentHeader, _userAgentGetter());

        QUrl grantURL = _authURL;
        grantURL.setPath(getMetaverseServerURLPath() + "/oauth/token");

        QByteArray postData;
        postData.append("grant_type=refresh_token&");
        postData.append("refresh_token=" + QUrl::toPercentEncoding(_accountInfo.getAccessToken().refreshToken) + "&");
        postData.append("scope=" + ACCOUNT_MANAGER_REQUESTED_SCOPE.toUtf8());

        request.setUrl(grantURL);
        request.setHeader(QNetworkRequest::ContentTypeHeader, "application/x-www-form-urlencoded");

        QNetworkReply* requestReply = networkAccessManager.post(request, postData);
        connect(requestReply, &QNetworkReply::finished, this, &AccountManager::refreshAccessTokenFinished);
#if QT_VERSION >= QT_VERSION_CHECK(5, 15, 0)
        connect(requestReply, &QNetworkReply::errorOccurred, this, &AccountManager::refreshAccessTokenError);
#else
        connect(requestReply, SIGNAL(error(QNetworkReply::NetworkError)), this, SLOT(refreshAccessTokenError(QNetworkReply::NetworkError)));
#endif
    } else {
        qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
    }
}

void AccountManager::setAccessTokens(const QString& response) {
    QJsonDocument jsonResponse = QJsonDocument::fromJson(response.toUtf8());
    const QJsonObject& rootObject = jsonResponse.object();

    if (!rootObject.contains("error")) {
        // construct an OAuthAccessToken from the json object

        if (!rootObject.contains("access_token") || !rootObject.contains("expires_in")
            || !rootObject.contains("token_type")) {
            // TODO: error handling - malformed token response
            qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
            qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
        } else {
            // clear the path from the response URL so we have the right root URL for this access token
            QUrl rootURL = rootObject.contains("url") ? rootObject["url"].toString() : _authURL;
            rootURL.setPath(getMetaverseServerURLPath());

            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

            _accountInfo = DataServerAccountInfo();
            _accountInfo.setAccessTokenFromJSON(rootObject);
            emit loginComplete(rootURL);

            persistAccountToFile();
            saveLoginStatus(true);
            requestProfile();
        }
    } else {
        // TODO: error handling
        qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
        emit loginFailed();
    }
}

void AccountManager::requestAccessTokenFinished() {
    QNetworkReply* requestReply = reinterpret_cast<QNetworkReply*>(sender());

    QJsonDocument jsonResponse = QJsonDocument::fromJson(requestReply->readAll());
    const QJsonObject& rootObject = jsonResponse.object();

    if (!rootObject.contains("error")) {
        // construct an OAuthAccessToken from the json object

        if (!rootObject.contains("access_token") || !rootObject.contains("expires_in")
            || !rootObject.contains("token_type")) {
            // TODO: error handling - malformed token response
            qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
            qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
        } else {
            // clear the path from the response URL so we have the right root URL for this access token
            QUrl rootURL = requestReply->url();
            rootURL.setPath(getMetaverseServerURLPath());

            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

            _accountInfo = DataServerAccountInfo();
            _accountInfo.setAccessTokenFromJSON(rootObject);

            emit loginComplete(rootURL);

            persistAccountToFile();

            requestProfile();
        }
    } else {
        // TODO: error handling
        qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
        emit loginFailed();
    }
}

void AccountManager::requestAccessTokenError(QNetworkReply::NetworkError error) {
    qCWarning(networking) << "AccountManager: failed to request access token -" << error;
    emit loginFailed();
}

void AccountManager::refreshAccessTokenFinished() {
    QNetworkReply* requestReply = reinterpret_cast<QNetworkReply*>(sender());

    QJsonDocument jsonResponse = QJsonDocument::fromJson(requestReply->readAll());
    const QJsonObject& rootObject = jsonResponse.object();

    if (!rootObject.contains("error")) {
        // construct an OAuthAccessToken from the json object

        if (!rootObject.contains("access_token") || !rootObject.contains("expires_in")
            || !rootObject.contains("token_type")) {
            // TODO: error handling - malformed token response
            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
        } else {
            // clear the path from the response URL so we have the right root URL for this access token
            QUrl rootURL = requestReply->url();
            rootURL.setPath(getMetaverseServerURLPath());

            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

            _accountInfo.setAccessTokenFromJSON(rootObject);

            persistAccountToFile();
        }
    } else {
        qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
    }

    _isWaitingForTokenRefresh = false;
}

void AccountManager::refreshAccessTokenError(QNetworkReply::NetworkError error) {
    // TODO: error handling
    qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
    _isWaitingForTokenRefresh = false;
}

void AccountManager::requestProfile() {
    QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();

    QUrl profileURL = _authURL;
    profileURL.setPath(getMetaverseServerURLPath() + "/api/v1/user/profile");

    QNetworkRequest profileRequest(profileURL);
    profileRequest.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::NoLessSafeRedirectPolicy);
    profileRequest.setHeader(QNetworkRequest::UserAgentHeader, _userAgentGetter());
    profileRequest.setRawHeader(ACCESS_TOKEN_AUTHORIZATION_HEADER, _accountInfo.getAccessToken().authorizationHeaderValue());

    QNetworkReply* profileReply = networkAccessManager.get(profileRequest);
    connect(profileReply, &QNetworkReply::finished, this, &AccountManager::requestProfileFinished);
#if QT_VERSION >= QT_VERSION_CHECK(5, 15, 0)
    connect(profileReply, &QNetworkReply::errorOccurred, this, &AccountManager::requestProfileError);
#else
    connect(profileReply, SIGNAL(error(QNetworkReply::NetworkError)), this, SLOT(requestProfileError(QNetworkReply::NetworkError)));
#endif
}

void AccountManager::requestProfileFinished() {
    QNetworkReply* profileReply = reinterpret_cast<QNetworkReply*>(sender());

    QJsonDocument jsonResponse = QJsonDocument::fromJson(profileReply->readAll());
    const QJsonObject& rootObject = jsonResponse.object();

    if (rootObject.contains("status") && rootObject["status"].toString() == "success") {
        _accountInfo.setProfileInfoFromJSON(rootObject);

        emit profileChanged();

        // the username has changed to whatever came back
        emit usernameChanged(_accountInfo.getUsername());

        // store the whole profile into the local settings
        persistAccountToFile();

    } else {
        // TODO: error handling
        qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
    }
}

void AccountManager::requestProfileError(QNetworkReply::NetworkError error) {
    // TODO: error handling
    qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
}

void AccountManager::requestAccountSettings() {
    if (!_accountSettingsEnabled) {
        return;
    }

    qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

    QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();

    QUrl lockerURL = _authURL;
    lockerURL.setPath(getMetaverseServerURLPath() + "/api/v1/user/locker");

    QNetworkRequest lockerRequest(lockerURL);
    lockerRequest.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::NoLessSafeRedirectPolicy);
    lockerRequest.setHeader(QNetworkRequest::UserAgentHeader, _userAgentGetter());
    lockerRequest.setRawHeader(ACCESS_TOKEN_AUTHORIZATION_HEADER, _accountInfo.getAccessToken().authorizationHeaderValue());

    QNetworkReply* lockerReply = networkAccessManager.get(lockerRequest);
    connect(lockerReply, &QNetworkReply::finished, this, &AccountManager::requestAccountSettingsFinished);
#if QT_VERSION >= QT_VERSION_CHECK(5, 15, 0)
    connect(lockerReply, &QNetworkReply::errorOccurred, this, &AccountManager::requestAccountSettingsError);
#else
    connect(lockerReply, SIGNAL(error(QNetworkReply::NetworkError)), this, SLOT(requestAccountSettingsError(QNetworkReply::NetworkError)));
#endif

    _settings.startedLoading();
}

void AccountManager::requestAccountSettingsFinished() {
    QNetworkReply* lockerReply = reinterpret_cast<QNetworkReply*>(sender());

    QJsonDocument jsonResponse = QJsonDocument::fromJson(lockerReply->readAll());
    const QJsonObject& rootObject = jsonResponse.object();

    if (rootObject.contains("status") && rootObject["status"].toString() == "success") {
        if (rootObject.contains("data") && rootObject["data"].isObject()) {
            _settings.unpack(rootObject["data"].toObject());
            _lastSuccessfulSyncTimestamp = _settings.lastChangeTimestamp();

            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

            emit accountSettingsLoaded();
        } else {
            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
            if (!_pullSettingsRetryTimer->isActive() && _numPullRetries < MAX_PULL_RETRIES) {
                ++_numPullRetries;
                _pullSettingsRetryTimer->start();
            }
        }
    } else {
        qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
        if (!_pullSettingsRetryTimer->isActive() && _numPullRetries < MAX_PULL_RETRIES) {
            ++_numPullRetries;
            _pullSettingsRetryTimer->start();
        }
    }
}

void AccountManager::requestAccountSettingsError(QNetworkReply::NetworkError error) {
    qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
    if (!_pullSettingsRetryTimer->isActive() && _numPullRetries < MAX_PULL_RETRIES) {
        ++_numPullRetries;
        _pullSettingsRetryTimer->start();
    }
}

void AccountManager::postAccountSettings() {
    if (!_accountSettingsEnabled) {
        return;
    }

    if (_settings.lastChangeTimestamp() <= _lastSuccessfulSyncTimestamp && _lastSuccessfulSyncTimestamp != 0) {
        // Nothing changed, skipping settings post
        return;
    }
    if (!isLoggedIn()) {
        qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
        return;
    }

    qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

    QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();

    QUrl lockerURL = _authURL;
    lockerURL.setPath(getMetaverseServerURLPath() + "/api/v1/user/locker");

    QNetworkRequest lockerRequest(lockerURL);
    lockerRequest.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::NoLessSafeRedirectPolicy);
    lockerRequest.setHeader(QNetworkRequest::UserAgentHeader, _userAgentGetter());
    lockerRequest.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    lockerRequest.setRawHeader(ACCESS_TOKEN_AUTHORIZATION_HEADER, _accountInfo.getAccessToken().authorizationHeaderValue());

    _currentSyncTimestamp = _settings.lastChangeTimestamp();
    QJsonObject dataObj;
    dataObj.insert("locker", _settings.pack());

    auto postData = QJsonDocument(dataObj).toJson(QJsonDocument::Compact);

    QNetworkReply* lockerReply = networkAccessManager.put(lockerRequest, postData);
    connect(lockerReply, &QNetworkReply::finished, this, &AccountManager::postAccountSettingsFinished);
#if QT_VERSION >= QT_VERSION_CHECK(5, 15, 0)
    connect(lockerReply, &QNetworkReply::errorOccurred, this, &AccountManager::postAccountSettingsError);
#else
    connect(lockerReply, SIGNAL(error(QNetworkReply::NetworkError)), this, SLOT(postAccountSettingsError(QNetworkReply::NetworkError)));
#endif
}

void AccountManager::postAccountSettingsFinished() {
    QNetworkReply* lockerReply = reinterpret_cast<QNetworkReply*>(sender());

    QJsonDocument jsonResponse = QJsonDocument::fromJson(lockerReply->readAll());
    const QJsonObject& rootObject = jsonResponse.object();

    if (rootObject.contains("status") && rootObject["status"].toString() == "success") {
        _lastSuccessfulSyncTimestamp = _currentSyncTimestamp;
    } else {
        qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
    }
}

void AccountManager::postAccountSettingsError(QNetworkReply::NetworkError error) {
    qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
}

void AccountManager::generateNewKeypair(bool isUserKeypair, const QUuid& domainID) {

    if (thread() != QThread::currentThread()) {
        QMetaObject::invokeMethod(this, "generateNewKeypair", Q_ARG(bool, isUserKeypair), Q_ARG(QUuid, domainID));
        return;
    }

    if (!isUserKeypair && domainID.isNull()) {
        qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
        return;
    }

    // Ensure openssl/Qt config is set up.
    QSslConfiguration::defaultConfiguration();

    // make sure we don't already have an outbound keypair generation request
    if (!_isWaitingForKeypairResponse) {
        _isWaitingForKeypairResponse = true;

        // clear the current private key
        qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
        _accountInfo.setPrivateKey(QByteArray());

        // Create a runnable keypair generated to create an RSA pair and exit.
        RSAKeypairGenerator* keypairGenerator = new RSAKeypairGenerator;

        if (!isUserKeypair) {
            _accountInfo.setDomainID(domainID);
        }

        // handle success or failure of keypair generation
        connect(keypairGenerator, &RSAKeypairGenerator::generatedKeypair, this,
            &AccountManager::processGeneratedKeypair);
        connect(keypairGenerator, &RSAKeypairGenerator::errorGeneratingKeypair, this,
            &AccountManager::handleKeypairGenerationError);

        static constexpr int RSA_THREAD_PRIORITY = 1;
        qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
        // Start on Qt's global thread pool.
        QThreadPool::globalInstance()->start(keypairGenerator, RSA_THREAD_PRIORITY);
    }
}

void AccountManager::processGeneratedKeypair(QByteArray publicKey, QByteArray privateKey) {

    qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

    // hold the private key to later set our directory services API account info if upload succeeds
    _pendingPublicKey = publicKey;
    _pendingPrivateKey = privateKey;
    uploadPublicKey();
}

void AccountManager::uploadPublicKey() {
    if (_pendingPrivateKey.isEmpty()) {
        return;
    }

    qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

    // upload the public key so data-web has an up-to-date key
    const QString USER_PUBLIC_KEY_UPDATE_PATH = "/api/v1/user/public_key";
    const QString DOMAIN_PUBLIC_KEY_UPDATE_PATH = "/api/v1/domains/%1/public_key";

    QString uploadPath;
    const auto& domainID = _accountInfo.getDomainID();
    if (domainID.isNull()) {
        uploadPath = USER_PUBLIC_KEY_UPDATE_PATH;
    } else {
        uploadPath = DOMAIN_PUBLIC_KEY_UPDATE_PATH.arg(uuidStringWithoutCurlyBraces(domainID));
    }

    // setup a multipart upload to send up the public key
    QHttpMultiPart* requestMultiPart = new QHttpMultiPart(QHttpMultiPart::FormDataType);

    QHttpPart publicKeyPart;
    publicKeyPart.setHeader(QNetworkRequest::ContentTypeHeader, QVariant("application/octet-stream"));

    publicKeyPart.setHeader(QNetworkRequest::ContentDispositionHeader,
                        QVariant("form-data; name=\"public_key\"; filename=\"public_key\""));
    publicKeyPart.setBody(_pendingPublicKey);
    requestMultiPart->append(publicKeyPart);

    // Currently broken? We don't have the temporary domain key.
    if (!domainID.isNull()) {
        const auto& key = getTemporaryDomainKey(domainID);
        QHttpPart apiKeyPart;
        publicKeyPart.setHeader(QNetworkRequest::ContentTypeHeader, QVariant("application/octet-stream"));
        apiKeyPart.setHeader(QNetworkRequest::ContentDispositionHeader,
                            QVariant("form-data; name=\"api_key\""));
        apiKeyPart.setBody(key.toUtf8());
        requestMultiPart->append(apiKeyPart);
    }

    // setup callback parameters so we know once the keypair upload has succeeded or failed
    JSONCallbackParameters callbackParameters;
    callbackParameters.callbackReceiver = this;
    callbackParameters.jsonCallbackMethod = "publicKeyUploadSucceeded";
    callbackParameters.errorCallbackMethod = "publicKeyUploadFailed";

    sendRequest(uploadPath, AccountManagerAuth::Optional, QNetworkAccessManager::PutOperation,
                callbackParameters, QByteArray(), requestMultiPart);
}

void AccountManager::publicKeyUploadSucceeded(QNetworkReply* reply) {
    qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

    // public key upload complete - store the matching private key and persist the account to settings
    _accountInfo.setPrivateKey(_pendingPrivateKey);
    _pendingPublicKey.clear();
    _pendingPrivateKey.clear();
    persistAccountToFile();

    // clear our waiting state
    _isWaitingForKeypairResponse = false;

    emit newKeypair();
}

void AccountManager::publicKeyUploadFailed(QNetworkReply* reply) {
    // the public key upload has failed
    qCritical() << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

    // we aren't waiting for a response any longer
    _isWaitingForKeypairResponse = false;
}

void AccountManager::handleKeypairGenerationError() {
    qCritical() << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

    // reset our waiting state for keypair response
    _isWaitingForKeypairResponse = false;
}

void AccountManager::setLimitedCommerce(bool isLimited) {
    _limitedCommerce = isLimited;
}

void AccountManager::saveLoginStatus(bool isLoggedIn) {
    if (!_configFileURL.isEmpty()) {
        QFile configFile(_configFileURL);
        configFile.open(QIODevice::ReadOnly | QIODevice::Text);
        QJsonParseError error;
        QJsonDocument jsonDocument = QJsonDocument::fromJson(configFile.readAll(), &error);
        configFile.close();
        QString launcherPath;
        if (error.error == QJsonParseError::NoError) {
            QJsonObject rootObject = jsonDocument.object();
            if (rootObject.contains("launcherPath")) {
                launcherPath = rootObject["launcherPath"].toString();
            }
            if (rootObject.contains("loggedIn")) {
                rootObject["loggedIn"] = isLoggedIn;
            }
            jsonDocument = QJsonDocument(rootObject);

        }
        configFile.open(QFile::WriteOnly | QFile::Text | QFile::Truncate);
        configFile.write(jsonDocument.toJson());
        configFile.close();
#if !defined(Q_OS_IOS)
        if (!isLoggedIn && !launcherPath.isEmpty()) {
            QProcess launcher;
            launcher.setProgram(launcherPath);
            launcher.startDetached();
            QMetaObject::invokeMethod(qApp, "quit", Qt::QueuedConnection);
        }
#endif
    }
}

bool AccountManager::hasKeyPair() const {
    return _accountInfo.hasPrivateKey();
}
