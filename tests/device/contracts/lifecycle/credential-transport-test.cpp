// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
// Whole production managers/headers and real Qt dispatch/replies. No network
// route is available. Account data and ATP are explicit dependency boundaries.
#include <QtCore/QtCore>
#include <QtNetwork/QtNetwork>
#include <cassert>
#include "libraries/networking/src/NetworkAccessManager.h"
#include "libraries/networking/src/OAuthNetworkAccessManager.h"
#include "libraries/networking/src/CredentialTransportPolicy.h"
const QByteArray ACCESS_TOKEN_AUTHORIZATION_HEADER = "Authorization";
namespace NetworkingConstants {
    const char* OVERTE_USER_AGENT = "contract-test";
    const QStringList IS_AUTHABLE_HOSTNAME { "overte.org" };
}
namespace MetaverseAPI {
    QUrl getCurrentMetaverseServerURL() { return QUrl("https://metaverse.invalid"); }
}
struct AccountManager {
    bool valid = false;
    bool hasValidAccessToken() const { return valid; }
    struct AccountInfo {
        struct Token { QByteArray authorizationHeaderValue() const { return "Bearer credential-canary"; } } token;
        const Token& getAccessToken() const { return token; }
    } info;
    const AccountInfo& getAccountInfo() const { return info; }
};
struct DependencyManager {
    template<class T> static T* get() { static T instance; return &instance; }
};
class AtpReply : public QNetworkReply {
public:
    explicit AtpReply(const QUrl&) { open(QIODevice::ReadOnly); }
    void abort() override {}
    qint64 readData(char*, qint64) override { return -1; }
};
#include "NetworkAccessManager.inc"
#include "OAuthNetworkAccessManager.inc"
#include "request-filter-auth.inc"
static void finishQueued() {
    QCoreApplication::processEvents();
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
}
static void denied(QNetworkReply* reply) {
    assert(dynamic_cast<overte::network::RejectedCredentialReply*>(reply));
    assert(reply->error() == QNetworkReply::ContentAccessDenied);
    assert(reply->url().isEmpty() && reply->request().rawHeader("Authorization").isEmpty());
    int failed = 0, finished = 0;
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
    int legacyFailed = 0;
    QObject::connect(reply, static_cast<void(QNetworkReply::*)(QNetworkReply::NetworkError)>(&QNetworkReply::error),
        [&] { ++legacyFailed; });
#endif

    QObject::connect(reply, &QNetworkReply::errorOccurred, [&] { ++failed; });
    QObject::connect(reply, &QNetworkReply::finished, [&] { ++finished; });
    assert(failed == 0 && finished == 0);
    finishQueued();
    assert(failed == 1 && finished == 1);
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
    assert(legacyFailed == 1);
#endif
    delete reply;
}
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    assert(isAuthableMetaverseURL(QUrl("https://metaverse.invalid/api/profile")));
    assert(isAuthableMetaverseURL(QUrl("https://overte.org/api/profile")));
    for (const auto& endpoint : {"http://metaverse.invalid/api/profile", "http://overte.org/api/profile",
            "https://user:password@metaverse.invalid/api/profile", "https://untrusted.invalid/api/profile"}) {
        assert(!isAuthableMetaverseURL(QUrl(endpoint)));
    }
    auto& generic = NetworkAccessManager::getInstance();
    assert(&generic == &NetworkAccessManager::getInstance());
    auto* oauth = OAuthNetworkAccessManager::getInstance();
    assert(oauth == OAuthNetworkAccessManager::getInstance());
    for (auto* manager : {&generic, static_cast<QNetworkAccessManager*>(oauth)}) {
        for (auto operation : {QNetworkAccessManager::GetOperation, QNetworkAccessManager::PostOperation,
                              QNetworkAccessManager::PutOperation, QNetworkAccessManager::DeleteOperation}) {
            QNetworkRequest request(QUrl("http://credential.invalid/private"));
            request.setRawHeader("Authorization", "Bearer credential-canary");
            QNetworkReply* reply = nullptr;
            if (operation == QNetworkAccessManager::GetOperation) reply = manager->get(request);
            if (operation == QNetworkAccessManager::PostOperation) reply = manager->post(request, "password-canary");
            if (operation == QNetworkAccessManager::PutOperation) reply = manager->put(request, "password-canary");
            if (operation == QNetworkAccessManager::DeleteOperation) reply = manager->deleteResource(request);
            denied(reply);
        }
        denied(manager->get(QNetworkRequest(QUrl("http://user:password@credential.invalid/private"))));
        QNetworkRequest publicRequest(QUrl("http://public.invalid/resource"));
        auto* publicReply = manager->get(publicRequest);
        assert(!dynamic_cast<overte::network::RejectedCredentialReply*>(publicReply));
        assert(!publicReply->request().hasRawHeader("Authorization"));
        publicReply->abort(); delete publicReply;
        for (const auto& endpoint : {"https://credential.invalid/private", "https://user:password@credential.invalid/private"}) {
            QNetworkRequest request{QUrl(endpoint)};
            request.setRawHeader("Authorization", "Bearer credential-canary");
            request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::NoLessSafeRedirectPolicy);
            auto* reply = manager->get(request);
            assert(!dynamic_cast<overte::network::RejectedCredentialReply*>(reply));
            assert(reply->request().attribute(QNetworkRequest::RedirectPolicyAttribute).toInt() ==
                QNetworkRequest::ManualRedirectPolicy);
            reply->abort(); delete reply;
        }
    }
    auto* account = DependencyManager::get<AccountManager>();
    account->valid = true;
    // Real OAuth injection call path goes through the guarded base manager.
    denied(oauth->get(QNetworkRequest(QUrl("http://metaverse.invalid/api/profile"))));
    auto* secured = oauth->get(QNetworkRequest(QUrl("https://metaverse.invalid/api/profile")));
    assert(secured->request().rawHeader("Authorization") == "Bearer credential-canary");
    assert(secured->request().attribute(QNetworkRequest::RedirectPolicyAttribute).toInt() ==
        QNetworkRequest::ManualRedirectPolicy);
    secured->abort(); delete secured;
    // Deletion by an error observer must not reach the later finished signal.
    auto* rejecting = new overte::network::RejectedCredentialReply(generic, QNetworkAccessManager::PostOperation);
    QPointer<QNetworkReply> guard(rejecting);
    int finished = 0;
    QObject::connect(rejecting, &QNetworkReply::errorOccurred, [&] { delete rejecting; });
    QObject::connect(rejecting, &QNetworkReply::finished, [&] { ++finished; });
    finishQueued();
    assert(!guard && finished == 0);
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
    auto* legacyRejecting = new overte::network::RejectedCredentialReply(generic, QNetworkAccessManager::PostOperation);
    QPointer<QNetworkReply> legacyGuard(legacyRejecting);
    QObject::connect(legacyRejecting,
        static_cast<void(QNetworkReply::*)(QNetworkReply::NetworkError)>(&QNetworkReply::error),
        [&] { delete legacyRejecting; });
    QObject::connect(legacyRejecting, &QNetworkReply::finished, [&] { ++finished; });
    finishQueued();
    assert(!legacyGuard && finished == 0);
#endif
}
