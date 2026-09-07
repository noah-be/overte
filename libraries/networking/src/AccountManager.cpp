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
#include "OAuthTokenValidation.h"

#include <memory>

#include <QtCore/QDataStream>
#include <QtCore/QDir>
#include <QtCore/QFile>
#include <QtCore/QFileInfo>
#include "../../../security/redaction/SafeDiagnostics.h"
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QMap>
#include <QtCore/QPointer>
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
    qRegisterMetaTypeStreamOperators<OAuthAccessToken>("OAuthAccessToken");

    qRegisterMetaType<DataServerAccountInfo>("DataServerAccountInfo");
    qRegisterMetaTypeStreamOperators<DataServerAccountInfo>("DataServerAccountInfo");

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

// One absolute event-loop deadline, not an inactivity timer. The reply owns
// the timer callback, so deletion cancels it without extending reply lifetime.
static void observeAccountTokenDeadline(QNetworkReply* reply) {
    QTimer::singleShot(15000, Qt::PreciseTimer, reply, [reply] {
        if (reply->isFinished()) {
            return;
        }
        // Abort may synchronously emit finished; fence it before that signal.
        reply->setProperty("_overte_account_auth_timed_out", true);
        const QPointer<QNetworkReply> survivingReply(reply);
        reply->abort();
        if (survivingReply) {
            survivingReply->deleteLater();
        }
    });
}

void AccountManager::resetAccountSettings() {
    _settingsGetContext.next();
    if (_pullSettingsRetryTimer) { _pullSettingsRetryTimer->stop(); }
    if (_postSettingsTimer) { _postSettingsTimer->stop(); }
    _settingsRetryCredentials = {};
    _settingsRetryRequest = {};
    _settingsSyncCredentials = {};
    _numPullRetries = 0;
    _lastSuccessfulSyncTimestamp = 0;
    _settings.loggedOut();
}

void AccountManager::logout() {
    const auto logoutContext = _credentialContext.next();
    QPointer<AccountManager> logoutOwner(this);
    _isWaitingForTokenRefresh = false;
    _isWaitingForAccessToken = false;
    postAccountSettings();
    if (!logoutOwner || !logoutContext.current()) { return; }
    resetAccountSettings();

    // a logout means we want to delete the DataServerAccountInfo we currently have for this URL, in-memory and in file
    _accountInfo = DataServerAccountInfo();

    // remove this account from the account settings file
    removeAccountFromFile();
    if (!logoutOwner || !logoutContext.current()) { return; }
    saveLoginStatus(false);
    if (!logoutOwner || !logoutContext.current()) { return; }

    emit logoutComplete();
    if (!logoutOwner || !logoutContext.current()) { return; }
    // the username has changed to blank
    emit usernameChanged(QString());
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

bool validAccountMapBytes(const overte::security::AccountBytes& bytes) {
    if (bytes.empty() || bytes.size() > overte::security::MAX_ACCOUNT_BYTES) { return false; }
    QByteArray serialized(reinterpret_cast<const char*>(bytes.data()), static_cast<int>(bytes.size()));
    QDataStream stream(serialized);
    QVariantMap checked;
    stream >> checked;
    const bool valid = stream.status() == QDataStream::Ok && stream.atEnd();
    serialized.fill('\0');
    if (!valid) { return false; }
    // The account map is a typed record, not an arbitrary QVariant container.
    // Reject wrong types before migration can discard recoverable legacy data.
    for (auto it = checked.cbegin(); it != checked.cend(); ++it) {
        if (it.value().userType() != qMetaTypeId<DataServerAccountInfo>()) { return false; }
    }
    return true;
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
        },
        validAccountMapBytes
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
        const auto context = _credentialContext.next();
        const QPointer<AccountManager> owner(this);
        resetAccountSettings();
        if (!owner || !context.current()) { return; }
        _isWaitingForTokenRefresh = false;
        _isWaitingForAccessToken = false;
        _authURL = authURL;

        qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

        if (!owner || !context.current()) { return; }
        // check if there are existing access tokens to load from settings
        bool loadedMap = false;
        auto accountsMap = accountMapFromFile(loadedMap);
        if (!owner || !context.current()) { return; }

        _accountInfo = DataServerAccountInfo();
        if (loadedMap) {
            // pull out the stored account info and store it in memory
            _accountInfo = accountsMap[_authURL.toString()].value<DataServerAccountInfo>();

            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
        } else {
            qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
            if (!owner || !context.current()) { return; }
            emit authRequired();
        }

        if (!owner || !context.current()) { return; }
        // Publish the loaded endpoint before starting requests, which acquire
        // their own credential generation. Reentrant listeners may supersede it.
        emit authEndpointChanged();
        if (!owner || !context.current()) { return; }
        if (_isAgent && !_accountInfo.getAccessToken().token.isEmpty() && !_accountInfo.hasProfile()) {
            // we are missing profile information, request it now
            requestProfile();
            if (!owner || !context.current()) { return; }
        }

        // prepare to refresh our token if it is about to expire
        if (needsToRefreshToken()) {
            refreshAccessToken();
            if (!owner || !context.current()) { return; }
        }

        if (isLoggedIn()) {
            emit loginComplete(_authURL);
            if (!owner || !context.current()) { return; }
        }

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
    // Failed persistence invalidates this credential transaction before re-auth
    // can reenter. Existing completion guards must not continue as a success.
    _credentialContext.next();
    _isWaitingForTokenRefresh = false;
    resetAccountSettings();
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
    const auto context = _credentialContext.next();
    const QPointer<AccountManager> owner(this);
    _isWaitingForAccessToken = false;
    _isWaitingForTokenRefresh = false;
    resetAccountSettings();
    if (!owner || !context.current()) { return; }
    _accountInfo = newAccountInfo;
    _pendingPrivateKey.clear();
    if (_isAgent && !_accountInfo.getAccessToken().token.isEmpty() && !_accountInfo.hasProfile()) {
        // we are missing profile information, request it now
        requestProfile();
        if (!owner || !context.current()) { return; }
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
    if (_accountInfo.getAccessToken().token != accessToken) {
        _credentialContext.next();
        _isWaitingForAccessToken = false;
        _isWaitingForTokenRefresh = false;
        resetAccountSettings();
    }
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
    const auto requestContext = _credentialContext.next();
    QPointer<AccountManager> requestOwner(this);
    _isWaitingForAccessToken = true;
    _isWaitingForTokenRefresh = false;

    QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();

    QNetworkRequest request;
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    request.setHeader(QNetworkRequest::UserAgentHeader, _userAgentGetter());
    if (!requestOwner || !requestContext.current()) { return; }

    QUrl grantURL = _authURL;
    grantURL.setPath(getMetaverseServerURLPath() + "/oauth/token");

    QByteArray postData;
    postData.append("grant_type=password&");
    postData.append("username=" + QUrl::toPercentEncoding(login) + "&");
    postData.append("password=" + QUrl::toPercentEncoding(password) + "&");
    postData.append("scope=" + ACCOUNT_MANAGER_REQUESTED_SCOPE.toUtf8());

    request.setUrl(grantURL);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/x-www-form-urlencoded");

    if (!requestOwner || !requestContext.current()) { return; }
    QNetworkReply* requestReply = networkAccessManager.post(request, postData);
    overte::network::watchRequest(requestReply, requestContext);
    observeAccountTokenDeadline(requestReply);
    if (!requestOwner || !requestContext.current()) { requestReply->deleteLater(); return; }
    connect(requestReply, &QNetworkReply::finished, this, &AccountManager::requestAccessTokenFinished);
    connect(requestReply, &QObject::destroyed, this, [this, requestContext] {
        if (requestContext.current()) { _isWaitingForAccessToken = false; }
    });
}

void AccountManager::requestAccessTokenWithAuthCode(const QString& authCode, const QString& clientId, const QString& clientSecret, const QString& redirectUri) {
    const auto requestContext = _credentialContext.next();
    QPointer<AccountManager> requestOwner(this);
    _isWaitingForAccessToken = true;
    _isWaitingForTokenRefresh = false;
    QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();

    QNetworkRequest request;
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    request.setHeader(QNetworkRequest::UserAgentHeader, _userAgentGetter());
    if (!requestOwner || !requestContext.current()) { return; }

    QUrl grantURL = _authURL;
    grantURL.setPath(getMetaverseServerURLPath() + "/oauth/token");

    QByteArray postData;
    postData.append("grant_type=authorization_code&");
    postData.append("client_id=" + QUrl::toPercentEncoding(clientId) + "&");
    postData.append("client_secret=" + QUrl::toPercentEncoding(clientSecret) + "&");
    postData.append("code=" + QUrl::toPercentEncoding(authCode) + "&");
    postData.append("redirect_uri=" + QUrl::toPercentEncoding(redirectUri));

    request.setUrl(grantURL);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/x-www-form-urlencoded");

    if (!requestOwner || !requestContext.current()) { return; }
    QNetworkReply* requestReply = networkAccessManager.post(request, postData);
    overte::network::watchRequest(requestReply, requestContext);
    observeAccountTokenDeadline(requestReply);
    if (!requestOwner || !requestContext.current()) { requestReply->deleteLater(); return; }
    connect(requestReply, &QNetworkReply::finished, this, &AccountManager::requestAccessTokenFinished);
    connect(requestReply, &QObject::destroyed, this, [this, requestContext] {
        if (requestContext.current()) { _isWaitingForAccessToken = false; }
    });
}

void AccountManager::requestAccessTokenWithSteam(QByteArray authSessionTicket) {
    const auto requestContext = _credentialContext.next();
    QPointer<AccountManager> requestOwner(this);
    _isWaitingForAccessToken = true;
    _isWaitingForTokenRefresh = false;
    QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();

    QNetworkRequest request;
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    request.setHeader(QNetworkRequest::UserAgentHeader, _userAgentGetter());
    if (!requestOwner || !requestContext.current()) { return; }

    QUrl grantURL = _authURL;
    grantURL.setPath(getMetaverseServerURLPath() + "/oauth/token");

    QByteArray postData;
    postData.append("grant_type=password&");
    postData.append("steam_auth_ticket=" + QUrl::toPercentEncoding(authSessionTicket) + "&");
    postData.append("scope=" + ACCOUNT_MANAGER_REQUESTED_SCOPE.toUtf8());

    request.setUrl(grantURL);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/x-www-form-urlencoded");

    if (!requestOwner || !requestContext.current()) { return; }
    QNetworkReply* requestReply = networkAccessManager.post(request, postData);
    overte::network::watchRequest(requestReply, requestContext);
    observeAccountTokenDeadline(requestReply);
    if (!requestOwner || !requestContext.current()) { requestReply->deleteLater(); return; }
    connect(requestReply, &QNetworkReply::finished, this, &AccountManager::requestAccessTokenFinished);
    connect(requestReply, &QObject::destroyed, this, [this, requestContext] {
        if (requestContext.current()) { _isWaitingForAccessToken = false; }
    });
}

void AccountManager::requestAccessTokenWithOculus(const QString& nonce, const QString &oculusID) {
    const auto requestContext = _credentialContext.next();
    QPointer<AccountManager> requestOwner(this);
    _isWaitingForAccessToken = true;
    _isWaitingForTokenRefresh = false;
    QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();

    QNetworkRequest request;
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    request.setHeader(QNetworkRequest::UserAgentHeader, _userAgentGetter());
    if (!requestOwner || !requestContext.current()) { return; }

    QUrl grantURL = _authURL;
    grantURL.setPath(getMetaverseServerURLPath() + "/oauth/token");

    QByteArray postData;
    postData.append("grant_type=password&");
    postData.append("oculus_nonce=" + QUrl::toPercentEncoding(nonce) + "&");
    postData.append("oculus_id=" + QUrl::toPercentEncoding(oculusID) + "&");
    postData.append("scope=" + ACCOUNT_MANAGER_REQUESTED_SCOPE.toUtf8());

    request.setUrl(grantURL);
    request.setHeader(QNetworkRequest::ContentTypeHeader, "application/x-www-form-urlencoded");

    if (!requestOwner || !requestContext.current()) { return; }
    QNetworkReply* requestReply = networkAccessManager.post(request, postData);
    overte::network::watchRequest(requestReply, requestContext);
    observeAccountTokenDeadline(requestReply);
    if (!requestOwner || !requestContext.current()) { requestReply->deleteLater(); return; }
    connect(requestReply, &QNetworkReply::finished, this, &AccountManager::requestAccessTokenFinished);
    connect(requestReply, &QObject::destroyed, this, [this, requestContext] {
        if (requestContext.current()) { _isWaitingForAccessToken = false; }
    });
}

void AccountManager::refreshAccessToken() {
    // Background refresh cannot overtake an explicit login intent or enqueue
    // another refresh against the same installed credentials.
    if (_isWaitingForAccessToken || _isWaitingForTokenRefresh) { return; }

    // we can't refresh our access token if we don't have a refresh token, so check for that first
    if (!_accountInfo.getAccessToken().refreshToken.isEmpty()) {
        qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

        _isWaitingForTokenRefresh = true;
        const auto requestContext = _credentialContext.next();
        QPointer<AccountManager> requestOwner(this);

        QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();

        QNetworkRequest request;
        request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
        request.setHeader(QNetworkRequest::UserAgentHeader, _userAgentGetter());
        if (!requestOwner || !requestContext.current()) { return; }

        QUrl grantURL = _authURL;
        grantURL.setPath(getMetaverseServerURLPath() + "/oauth/token");

        QByteArray postData;
        postData.append("grant_type=refresh_token&");
        postData.append("refresh_token=" + QUrl::toPercentEncoding(_accountInfo.getAccessToken().refreshToken) + "&");
        postData.append("scope=" + ACCOUNT_MANAGER_REQUESTED_SCOPE.toUtf8());

        request.setUrl(grantURL);
        request.setHeader(QNetworkRequest::ContentTypeHeader, "application/x-www-form-urlencoded");

        QNetworkReply* requestReply = networkAccessManager.post(request, postData);
        overte::network::watchRequest(requestReply, requestContext);
        observeAccountTokenDeadline(requestReply);
        if (!requestOwner || !requestContext.current()) { requestReply->deleteLater(); return; }
        connect(requestReply, &QNetworkReply::finished, this, &AccountManager::refreshAccessTokenFinished);
        connect(requestReply, &QObject::destroyed, this, [this, requestContext] {
            if (requestContext.current()) { _isWaitingForTokenRefresh = false; }
        });
        connect(requestReply, SIGNAL(error(QNetworkReply::NetworkError)), this, SLOT(refreshAccessTokenError(QNetworkReply::NetworkError)));
    } else {
        qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
    }
}

bool AccountManager::setAccessTokens(const QString& response) {
    constexpr int MAX_RESPONSE_BYTES = 1024 * 1024;
    // Bound conversion first, then validate the actual UTF8 byte size.
    if (response.size() > MAX_RESPONSE_BYTES) {
        emit loginFailed();
        return false;
    }
    const auto payload = response.toUtf8();
    if (payload.size() > MAX_RESPONSE_BYTES) {
        emit loginFailed();
        return false;
    }
    QJsonParseError parseError;
    QJsonDocument jsonResponse = QJsonDocument::fromJson(payload, &parseError);
    if (parseError.error != QJsonParseError::NoError || !jsonResponse.isObject()) {
        emit loginFailed();
        return false;
    }
    const QJsonObject& rootObject = jsonResponse.object();

    if (!rootObject.contains("error")) {
        // construct an OAuthAccessToken from the json object

        if (!overte::network::validOAuthTokenResponse(rootObject)) {
            qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
            qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
            emit loginFailed();
        } else {
            // clear the path from the response URL so we have the right root URL for this access token
            QUrl rootURL = rootObject.contains("url") ? rootObject["url"].toString() : _authURL;
            rootURL.setPath(getMetaverseServerURLPath());

            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

            const auto completionContext = _credentialContext.next();
            _isWaitingForAccessToken = false;
            _isWaitingForTokenRefresh = false;
            resetAccountSettings();
            _accountInfo = DataServerAccountInfo();
            _accountInfo.setAccessTokenFromJSON(rootObject);
            QPointer<AccountManager> completionOwner(this);
            // Do not publish successful login before protected persistence.
            persistAccountToFile();
            if (!completionOwner || !completionContext.current()) {
                return false;
            }

            emit loginComplete(rootURL);
            if (!completionOwner || !completionContext.current()) {
                return false;
            }
            saveLoginStatus(true);
            if (!completionOwner || !completionContext.current()) {
                return false;
            }
            requestProfile();
            return completionOwner && completionContext.current();
        }
    } else {
        // TODO: error handling
        qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
        emit loginFailed();
    }
    return false;
}

void AccountManager::requestAccessTokenFinished() {
    auto* requestReply = qobject_cast<QNetworkReply*>(sender());
    if (!requestReply || requestReply->property("_overte_account_auth_finished").toBool()) {
        return;
    }
    requestReply->setProperty("_overte_account_auth_finished", true);
    requestReply->deleteLater();
    if (!overte::network::replyCurrent(requestReply)) {
        return;
    }
    _isWaitingForAccessToken = false;

    constexpr qint64 MAX_RESPONSE_BYTES = 1024 * 1024;
    const auto payload = requestReply->read(MAX_RESPONSE_BYTES + 1);
    QJsonParseError parseError;
    QJsonDocument jsonResponse = QJsonDocument::fromJson(payload, &parseError);
    const int status = requestReply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    if (requestReply->property("_overte_account_auth_timed_out").toBool() ||
            requestReply->error() != QNetworkReply::NoError || status < 200 || status >= 300 ||
            payload.size() > MAX_RESPONSE_BYTES || requestReply->bytesAvailable() != 0 ||
            parseError.error != QJsonParseError::NoError || !jsonResponse.isObject()) {
        emit loginFailed();
        return;
    }
    const QJsonObject& rootObject = jsonResponse.object();

    if (!rootObject.contains("error")) {
        // construct an OAuthAccessToken from the json object

        // QJsonValue::toInt rejects fractions and values outside signed 32-bit
        // seconds. This also bounds the downstream seconds-to-milliseconds
        // conversion; presence alone must not turn an invalid token into login.
        if (!overte::network::validOAuthTokenResponse(rootObject)) {
            qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
            qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
            emit loginFailed();
        } else {
            // clear the path from the response URL so we have the right root URL for this access token
            QUrl rootURL = requestReply->url();
            rootURL.setPath(getMetaverseServerURLPath());

            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

            resetAccountSettings();
            _accountInfo = DataServerAccountInfo();
            _accountInfo.setAccessTokenFromJSON(rootObject);

            const auto completionContext = _credentialContext.snapshot();
            QPointer<AccountManager> completionOwner(this);
            // The failure path invalidates this snapshot and requests re-auth.
            persistAccountToFile();
            if (!completionOwner || !completionContext.current()) {
                return;
            }

            emit loginComplete(rootURL);
            if (!completionOwner || !completionContext.current()) {
                return;
            }

            requestProfile();
        }
    } else {
        // TODO: error handling
        qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
        emit loginFailed();
    }
}

void AccountManager::refreshAccessTokenFinished() {
    auto* requestReply = qobject_cast<QNetworkReply*>(sender());
    if (!requestReply || requestReply->property("_overte_account_refresh_finished").toBool()) {
        return;
    }
    requestReply->setProperty("_overte_account_refresh_finished", true);
    requestReply->deleteLater();
    if (!overte::network::replyCurrent(requestReply)) {
        return;
    }
    _isWaitingForTokenRefresh = false;

    constexpr qint64 MAX_RESPONSE_BYTES = 1024 * 1024;
    const auto payload = requestReply->read(MAX_RESPONSE_BYTES + 1);
    QJsonParseError parseError;
    QJsonDocument jsonResponse = QJsonDocument::fromJson(payload, &parseError);
    const int status = requestReply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    if (requestReply->property("_overte_account_auth_timed_out").toBool() ||
            requestReply->error() != QNetworkReply::NoError || status < 200 || status >= 300 ||
            payload.size() > MAX_RESPONSE_BYTES || requestReply->bytesAvailable() != 0 ||
            parseError.error != QJsonParseError::NoError || !jsonResponse.isObject()) {
        return;
    }
    const QJsonObject& rootObject = jsonResponse.object();

    if (!rootObject.contains("error")) {
        // construct an OAuthAccessToken from the json object

        if (!overte::network::validOAuthTokenResponse(rootObject)) {
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

}

void AccountManager::refreshAccessTokenError(QNetworkReply::NetworkError error) {
    const auto* reply = qobject_cast<QNetworkReply*>(sender());
    if (!reply || !overte::network::replyCurrent(reply)) {
        return;
    }
    // TODO: error handling
    qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
    _isWaitingForTokenRefresh = false;
}

void AccountManager::requestProfile() {
    if (_isWaitingForAccessToken) { return; }
    const auto credentials = _credentialContext.snapshot();
    const auto profileContext = _profileContext.next();
    QPointer<AccountManager> owner(this);
    QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();

    QUrl profileURL = _authURL;
    profileURL.setPath(getMetaverseServerURLPath() + "/api/v1/user/profile");

    QNetworkRequest profileRequest(profileURL);
    profileRequest.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    profileRequest.setHeader(QNetworkRequest::UserAgentHeader, _userAgentGetter());
    if (!owner || !credentials.current() || !profileContext.current()) { return; }
    profileRequest.setRawHeader(ACCESS_TOKEN_AUTHORIZATION_HEADER, _accountInfo.getAccessToken().authorizationHeaderValue());

    QNetworkReply* profileReply = networkAccessManager.get(profileRequest);
    // Both lifetimes must remain current. Each watcher retains its own ticket;
    // replyCurrent checks the final (profile) ticket, credentials are explicit.
    profileReply->setProperty("_overte_profile_credentials", QVariant::fromValue(credentials));
    overte::network::watchRequest(profileReply, credentials);
    overte::network::watchRequest(profileReply, profileContext);
    observeAccountTokenDeadline(profileReply);
    if (!owner || !credentials.current() || !profileContext.current()) { profileReply->deleteLater(); return; }
    connect(profileReply, &QNetworkReply::finished, this, &AccountManager::requestProfileFinished);
    connect(profileReply, SIGNAL(error(QNetworkReply::NetworkError)), this, SLOT(requestProfileError(QNetworkReply::NetworkError)));
}

void AccountManager::requestProfileFinished() {
    auto* profileReply = qobject_cast<QNetworkReply*>(sender());
    if (!profileReply || profileReply->property("_overte_profile_finished").toBool()) { return; }
    profileReply->setProperty("_overte_profile_finished", true);
    profileReply->deleteLater();
    const auto credentials = profileReply->property("_overte_profile_credentials").value<overte::network::RequestTicket>();
    const auto profileContext = profileReply->property("_overte_request_ticket").value<overte::network::RequestTicket>();
    if (!credentials.current() || !profileContext.current() ||
            !credentials.sameRequest(_credentialContext.snapshot()) ||
            !profileContext.sameRequest(_profileContext.snapshot())) { return; }
    QPointer<AccountManager> owner(this);
    QPointer<QNetworkReply> survivingReply(profileReply);
    constexpr qint64 MAX_PROFILE_BYTES = 1024 * 1024;
    const auto payload = profileReply->read(MAX_PROFILE_BYTES + 1);
    if (!owner || !survivingReply || !credentials.current() || !profileContext.current()) { return; }
    const int status = profileReply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    QJsonParseError parseError;
    QJsonDocument jsonResponse = QJsonDocument::fromJson(payload, &parseError);
    if (profileReply->property("_overte_account_auth_timed_out").toBool() ||
            profileReply->error() != QNetworkReply::NoError || status < 200 || status >= 300 ||
            payload.size() > MAX_PROFILE_BYTES || profileReply->bytesAvailable() != 0 ||
            parseError.error != QJsonParseError::NoError || !jsonResponse.isObject() ||
            !owner || !credentials.current() || !profileContext.current()) { return; }
    const QJsonObject& rootObject = jsonResponse.object();

    const auto user = rootObject.value("data").toObject().value("user").toObject();
    if (rootObject.value("status").toString() == "success" &&
            user.value("username").isString() && !user.value("username").toString().isEmpty()) {
        _accountInfo.setProfileInfoFromJSON(rootObject);

        persistAccountToFile();
        if (!owner || !credentials.current() || !profileContext.current()) { return; }
        emit profileChanged();
        if (!owner || !credentials.current() || !profileContext.current()) { return; }

        // the username has changed to whatever came back
        emit usernameChanged(_accountInfo.getUsername());

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
    if (!_accountSettingsEnabled || _isPostingAccountSettings || _isWaitingForAccessToken || !isLoggedIn()) {
        return;
    }
    const auto credentials = _credentialContext.snapshot();
    if (sender() == _pullSettingsRetryTimer &&
        (!_settingsRetryCredentials.current() || !_settingsRetryCredentials.sameRequest(credentials) ||
         !_settingsRetryRequest.current() || !_settingsRetryRequest.sameRequest(_settingsGetContext.snapshot()))) {
        return;
    }
    if (sender() != _pullSettingsRetryTimer) { _numPullRetries = 0; }
    _pullSettingsRetryTimer->stop();
    const auto download = _settingsGetContext.next();
    QPointer<AccountManager> owner(this);
    quint64 requestedTimestamp = 0;
    if (!_settings.beginDownload(requestedTimestamp)) {
        _numPullRetries = 0;
        _postSettingsTimer->start();
        return;
    }

    qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

    QNetworkAccessManager& networkAccessManager = NetworkAccessManager::getInstance();

    QUrl lockerURL = _authURL;
    lockerURL.setPath(getMetaverseServerURLPath() + "/api/v1/user/locker");

    QNetworkRequest lockerRequest(lockerURL);
    lockerRequest.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    lockerRequest.setHeader(QNetworkRequest::UserAgentHeader, _userAgentGetter());
    if (!owner || !credentials.current() || !download.current()) { return; }
    lockerRequest.setRawHeader(ACCESS_TOKEN_AUTHORIZATION_HEADER, _accountInfo.getAccessToken().authorizationHeaderValue());

    QNetworkReply* lockerReply = networkAccessManager.get(lockerRequest);
    lockerReply->setProperty("_overte_settings_requested_timestamp", QVariant::fromValue(requestedTimestamp));
    lockerReply->setProperty("_overte_settings_credentials", QVariant::fromValue(credentials));
    overte::network::watchRequest(lockerReply, credentials);
    overte::network::watchRequest(lockerReply, download);
    observeAccountTokenDeadline(lockerReply);
    if (!owner || !credentials.current() || !download.current()) { lockerReply->deleteLater(); return; }
    connect(lockerReply, &QNetworkReply::finished, this, &AccountManager::requestAccountSettingsFinished);
    connect(lockerReply, SIGNAL(error(QNetworkReply::NetworkError)), this, SLOT(requestAccountSettingsError(QNetworkReply::NetworkError)));
}

void AccountManager::requestAccountSettingsFinished() {
    auto* lockerReply = qobject_cast<QNetworkReply*>(sender());
    if (!lockerReply || lockerReply->property("_overte_settings_get_finished").toBool()) { return; }
    lockerReply->setProperty("_overte_settings_get_finished", true);
    lockerReply->deleteLater();
    const auto download = lockerReply->property("_overte_request_ticket").value<overte::network::RequestTicket>();
    const auto credentials = lockerReply->property("_overte_settings_credentials").value<overte::network::RequestTicket>();
    if (!download.current() || !download.sameRequest(_settingsGetContext.snapshot()) ||
        !credentials.current() || !credentials.sameRequest(_credentialContext.snapshot())) { return; }
    QPointer<AccountManager> owner(this);
    QPointer<QNetworkReply> replyOwner(lockerReply);
    const auto response = lockerReply->read(1024 * 1024 + 1);
    if (!owner || !replyOwner || !download.current() || !credentials.current()) { return; }
    bool timestampValid = false;
    const auto requestedTimestamp = lockerReply->property("_overte_settings_requested_timestamp").toULongLong(&timestampValid);
    if (!timestampValid) { return; }
    if (_settings.lastChangeTimestamp() != requestedTimestamp) {
        // A local edit wins even over a failed GET. Retrying that GET would
        // capture the newer stamp and could overwrite the retained local value.
        _pullSettingsRetryTimer->stop();
        _numPullRetries = 0;
        if (_settings.homeLocationState() == AccountSettings::Loaded) { _postSettingsTimer->start(); }
        return;
    }
    const int status = lockerReply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    QJsonParseError parseError;
    QJsonDocument jsonResponse = QJsonDocument::fromJson(response, &parseError);
    const bool valid = !lockerReply->property("_overte_account_auth_timed_out").toBool() &&
        lockerReply->error() == QNetworkReply::NoError && status >= 200 && status < 300 &&
        response.size() <= 1024 * 1024 && lockerReply->bytesAvailable() == 0 &&
        parseError.error == QJsonParseError::NoError && jsonResponse.isObject();
    const QJsonObject& rootObject = jsonResponse.object();

    if (valid && rootObject.contains("status") && rootObject["status"].toString() == "success") {
        if (rootObject.contains("data") && rootObject["data"].isObject()) {
            quint64 appliedTimestamp = 0;
            if (!_settings.unpackIfUnchanged(rootObject["data"].toObject(), requestedTimestamp, appliedTimestamp)) {
                if (_settings.homeLocationState() == AccountSettings::Loaded) { _postSettingsTimer->start(); }
                return;
            }
            _lastSuccessfulSyncTimestamp = appliedTimestamp;
            _settingsSyncCredentials = credentials;
            _pullSettingsRetryTimer->stop();
            _numPullRetries = 0;

            qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);

            emit accountSettingsLoaded();
            return;
        }
    }
    qCDebug(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
    if (_numPullRetries < MAX_PULL_RETRIES) {
        _settingsRetryCredentials = credentials;
        _settingsRetryRequest = download;
        ++_numPullRetries;
        _pullSettingsRetryTimer->start();
    } else {
        _pullSettingsRetryTimer->stop();
        _settingsRetryCredentials = {};
        _settingsRetryRequest = {};
        _settings.downloadFailed(requestedTimestamp);
        // Future explicit edits may upload; failure itself emits no loaded signal.
        _postSettingsTimer->start();
    }
}

void AccountManager::requestAccountSettingsError(QNetworkReply::NetworkError error) {
    qCWarning(networking) << overte::security::diagnosticEvent(overte::security::DiagnosticEvent::Redacted);
    // The scoped finished receiver alone schedules retries, once per reply.
}

void AccountManager::postAccountSettings() {
    if (!_accountSettingsEnabled || _isPostingAccountSettings || _isWaitingForAccessToken) {
        return;
    }
    const auto settingsState = _settings.homeLocationState();
    if (settingsState == AccountSettings::LoggedOut || settingsState == AccountSettings::Loading) { return; }

    const auto credentials = _credentialContext.snapshot();
    if (!_settingsSyncCredentials.sameRequest(credentials)) {
        _lastSuccessfulSyncTimestamp = 0;
        _settingsSyncCredentials = credentials;
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
    const auto upload = _settingsPostContext.next();
    _settingsGetContext.next();
    _pullSettingsRetryTimer->stop();
    QPointer<AccountManager> owner(this);
    _isPostingAccountSettings = true;
    lockerRequest.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    lockerRequest.setHeader(QNetworkRequest::UserAgentHeader, _userAgentGetter());
    if (!owner) { return; }
    if (!credentials.current()) { _isPostingAccountSettings = false; return; }
    lockerRequest.setHeader(QNetworkRequest::ContentTypeHeader, "application/json");
    lockerRequest.setRawHeader(ACCESS_TOKEN_AUTHORIZATION_HEADER, _accountInfo.getAccessToken().authorizationHeaderValue());

    const auto snapshot = _settings.snapshot();
    QJsonObject dataObj;
    dataObj.insert("locker", snapshot.data);

    auto postData = QJsonDocument(dataObj).toJson(QJsonDocument::Compact);

    QNetworkReply* lockerReply = networkAccessManager.put(lockerRequest, postData);
    lockerReply->setProperty("_overte_settings_credentials", QVariant::fromValue(credentials));
    lockerReply->setProperty("_overte_settings_timestamp", QVariant::fromValue(snapshot.timestamp));
    overte::network::watchRequest(lockerReply, upload);
    observeAccountTokenDeadline(lockerReply);
    if (!owner) { lockerReply->deleteLater(); return; }
    connect(lockerReply, &QObject::destroyed, this, [this, upload] {
        if (upload.current()) { _isPostingAccountSettings = false; }
    });
    if (!credentials.current()) { lockerReply->deleteLater(); return; }
    connect(lockerReply, &QNetworkReply::finished, this, &AccountManager::postAccountSettingsFinished);
    connect(lockerReply, SIGNAL(error(QNetworkReply::NetworkError)), this, SLOT(postAccountSettingsError(QNetworkReply::NetworkError)));
}

void AccountManager::postAccountSettingsFinished() {
    auto* lockerReply = qobject_cast<QNetworkReply*>(sender());
    if (!lockerReply || lockerReply->property("_overte_settings_finished").toBool()) { return; }
    lockerReply->setProperty("_overte_settings_finished", true);
    lockerReply->deleteLater();
    const auto upload = lockerReply->property("_overte_request_ticket").value<overte::network::RequestTicket>();
    if (!upload.current() || !upload.sameRequest(_settingsPostContext.snapshot())) { return; }
    _isPostingAccountSettings = false;
    const auto credentials = lockerReply->property("_overte_settings_credentials").value<overte::network::RequestTicket>();
    if (!credentials.current() || !credentials.sameRequest(_credentialContext.snapshot())) { return; }
    const int status = lockerReply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
    if (lockerReply->error() != QNetworkReply::NoError || status < 200 || status >= 300 ||
        lockerReply->property("_overte_account_auth_timed_out").toBool()) { return; }
    QPointer<AccountManager> owner(this);
    QPointer<QNetworkReply> replyOwner(lockerReply);
    const auto response = lockerReply->read(1024 * 1024 + 1);
    if (!owner || !replyOwner || !credentials.current() || !upload.current()) { return; }
    if (response.size() > 1024 * 1024 || lockerReply->bytesAvailable() != 0) { return; }
    QJsonParseError parseError;
    QJsonDocument jsonResponse = QJsonDocument::fromJson(response, &parseError);
    if (parseError.error != QJsonParseError::NoError || !jsonResponse.isObject()) { return; }
    const QJsonObject& rootObject = jsonResponse.object();

    if (rootObject.contains("status") && rootObject["status"].toString() == "success") {
        _lastSuccessfulSyncTimestamp = lockerReply->property("_overte_settings_timestamp").toULongLong();
        _settings.acknowledgeSnapshot(_lastSuccessfulSyncTimestamp);
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
        if (!isLoggedIn && !launcherPath.isEmpty()) {
            QProcess launcher;
            launcher.setProgram(launcherPath);
            launcher.startDetached();
            QMetaObject::invokeMethod(qApp, "quit", Qt::QueuedConnection);
        }
    }
}

bool AccountManager::hasKeyPair() const {
    return _accountInfo.hasPrivateKey();
}
