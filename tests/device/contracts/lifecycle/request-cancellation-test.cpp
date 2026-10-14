// SPDX-License-Identifier: Apache-2.0
// Real Qt reply/timers and ORIGINAL production sendRequest body; network I/O is
// replaced solely at QNetworkAccessManager::createRequest, never by a real host.
#include <cassert>
#include <thread>
#include <vector>
#include <QtCore/QCoreApplication>
#include <QtCore/QEventLoop>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QLoggingCategory>
#include <QtCore/QPointer>
#include <QtCore/QThread>
#include <QtCore/QUuid>
#include <QtNetwork/QHttpMultiPart>
#include <QtCore/QUrlQuery>
#include <QtNetwork/QNetworkAccessManager>
#include "libraries/networking/src/CredentialTransportPolicy.h"
#include "libraries/networking/src/RequestCancellation.h"
#include "security/redaction/SafeDiagnostics.h"
#include "callback-parameters.inc"
namespace AccountManagerAuth { enum Type { None, Required, Optional, Credentials }; }
Q_DECLARE_METATYPE(AccountManagerAuth::Type)
Q_DECLARE_METATYPE(JSONCallbackParameters)
Q_LOGGING_CATEGORY(networking, "request-scope-test")
const bool VERBOSE_HTTP_REQUEST_DEBUGGING = false;
const QByteArray ACCESS_TOKEN_AUTHORIZATION_HEADER("Authorization");
QString uuidStringWithoutCurlyBraces(const QUuid& id) { return id.toString(QUuid::WithoutBraces); }
QUrl getMetaverseServerURL() { return QUrl("https://public-api.invalid"); }
QString getMetaverseServerURLPath(bool trailing = false) { return trailing ? "/api/" : "/api"; }
const QByteArray METAVERSE_SESSION_ID_HEADER("Test-Session-Only");
const QUuid initialSession("{11111111-2222-3333-4444-555555555555}");
const QUuid updatedSession("{66666666-7777-8888-9999-aaaaaaaaaaaa}");
int sent = 0, aborted = 0;
class FakeReply : public QNetworkReply {
public:
    FakeReply(QObject* parent) : QNetworkReply(parent) { open(QIODevice::ReadOnly); }
    void abort() override { if (!isFinished()) { ++aborted; setError(OperationCanceledError, "test-only"); finish(); } }
    void finish() { setFinished(true); emit finished(); }
    void sessionHeader() { setRawHeader(METAVERSE_SESSION_ID_HEADER, updatedSession.toString().toLatin1()); }
    qint64 readData(char*, qint64) override { return 0; }
};
class FakeNetwork : public QNetworkAccessManager {
public:
    QPointer<FakeReply> last;
    QNetworkRequest observed;
    Operation observedOperation {};
    QNetworkReply* createRequest(Operation operation, const QNetworkRequest& request, QIODevice*) override {
        observed = request; observedOperation = operation;
        ++sent; last = new FakeReply(this); return last;
    }
};
struct NetworkAccessManager { static QNetworkAccessManager& getInstance(); };
FakeNetwork* fakeNetwork;
QNetworkAccessManager& NetworkAccessManager::getInstance() { return *fakeNetwork; }
class AccountManager : public QObject {
public:
#include "account-session-field.inc"
    QUrl _authURL { "https://api.invalid" };
    bool tokenValid = false;
    QString _userAgentGetter() { return "contract-test"; }
    bool hasValidAccessToken() const { return tokenValid; }
    struct AccountInfo {
        struct Token { QByteArray authorizationHeaderValue() const { return "Bearer token-canary"; } } token;
        const Token& getAccessToken() const { return token; }
    } _accountInfo;
    QNetworkRequest createRequest(QString, AccountManagerAuth::Type);
    void sendRequest(const QString&, AccountManagerAuth::Type, QNetworkAccessManager::Operation,
                     const JSONCallbackParameters&, const QByteArray&, QHttpMultiPart*, const QVariantMap&);
};
class Receiver : public QObject {
    Q_OBJECT
public:
    int delivered = 0, failed = 0;
    Q_INVOKABLE void success(QNetworkReply*) { ++delivered; }
    Q_INVOKABLE void error(QNetworkReply* reply) { ++delivered; ++failed; assert(reply->error() != QNetworkReply::NoError); }
};
class AddressManager : public QObject {
public:
    overte::network::RequestScope _lookupRequests;
    bool _clientLookupPolicy { false }, _lookupForeground { true }, _lookupNeedsExplicitIntent { false };
    QUrl _previousAPILookup;
    void setClientLookupVisibility(bool);
    JSONCallbackParameters apiCallbackParameters();
};
#include "account-send-request.inc"
#include "address-request-methods.inc"
void events() { QEventLoop loop; QTimer::singleShot(80, &loop, &QEventLoop::quit); loop.exec(); }
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    FakeNetwork transport; fakeNetwork = &transport;
    AccountManager manager;
    manager._sessionID = initialSession;
    Receiver receiver;
    overte::network::RequestScope scope;
    JSONCallbackParameters callback(&receiver, "success", "error");
    auto send = [&] { manager.sendRequest("/test-only", AccountManagerAuth::None,
        QNetworkAccessManager::GetOperation, callback, QByteArray(), nullptr, QVariantMap()); };
    callback.requestTicket = scope.next();
    scope.setActive(false);
    assert(!callback.requestTicket.current()); send(); assert(sent == 0); // queued stale request never reaches I/O
    scope.setActive(true);
    callback.requestTicket = scope.next(); send(); assert(sent == 1);
    auto current = callback.requestTicket;
    scope.setActive(true); assert(current.current()); // duplicate visibility preserves work
    auto replacement = scope.next(); assert(!current.current() && replacement.current());
    assert(!overte::network::replyCurrent(transport.last));
    transport.last->sessionHeader(); transport.last->finish();
    assert(receiver.delivered == 0 && manager._sessionID == initialSession);
    events();
    callback.requestTicket = scope.next(); send();
    scope.setActive(false); assert(!callback.requestTicket.current());
    events(); assert(aborted == 1 && receiver.delivered == 0); // actual reply::abort timer, no stale callbacks
    scope.setActive(true); callback.requestTicket = scope.next(); send();
    transport.last->sessionHeader();
    transport.last->finish(); assert(receiver.delivered == 1); events(); // valid original callback still works
    assert(manager._sessionID == updatedSession);
    manager._sessionID = initialSession;
    auto temporary = new Receiver;
    callback = JSONCallbackParameters(temporary, "success", "error");
    callback.requestTicket = scope.next(); send();
    transport.last->sessionHeader();
    delete temporary; events(); assert(aborted == 2 && transport.last.isNull());
    assert(manager._sessionID == initialSession);
    callback = JSONCallbackParameters(&receiver, "success", "error");
    send(); transport.last->finish(); assert(receiver.delivered == 2); events(); // unscoped compatibility
    overte::network::RequestTicket destroyed;
    { overte::network::RequestScope shortScope; destroyed = shortScope.next(); assert(destroyed.current()); }
    assert(!destroyed.current());
    // Complete production request creation and dispatch. Optional anonymous
    // HTTP remains usable, while every bearer-bearing operation is rejected
    // before QNetworkAccessManager receives it, with its normal error callback.
    const auto beforeCredentialMatrix = sent;
    manager._authURL = QUrl("http://public-api.invalid");
    manager.tokenValid = false;
    callback = JSONCallbackParameters(&receiver, "success", "error");
    for (auto auth : {AccountManagerAuth::None, AccountManagerAuth::Optional}) {
        manager.sendRequest("/public", auth, QNetworkAccessManager::GetOperation,
            callback, {}, nullptr, {});
        assert(!transport.observed.hasRawHeader(ACCESS_TOKEN_AUTHORIZATION_HEADER));
        assert(transport.observed.attribute(QNetworkRequest::RedirectPolicyAttribute).toInt() ==
            QNetworkRequest::NoLessSafeRedirectPolicy);
        transport.last->finish(); events();
    }
    assert(sent == beforeCredentialMatrix + 2);
    manager.tokenValid = true;
    for (auto auth : {AccountManagerAuth::Optional, AccountManagerAuth::Required, AccountManagerAuth::Credentials}) {
        for (auto operation : {QNetworkAccessManager::GetOperation, QNetworkAccessManager::PostOperation,
                QNetworkAccessManager::PutOperation, QNetworkAccessManager::DeleteOperation}) {
            const auto before = sent;
            const auto failedBefore = receiver.failed;
            manager.sendRequest("/private", auth, operation, callback, "private-body-canary", nullptr, {});
            assert(sent == before && receiver.failed == failedBefore);
            events();
            assert(sent == before && receiver.failed == failedBefore + 1);
        }
    }
    {
        QPointer<QHttpMultiPart> multipart = new QHttpMultiPart;
        const auto before = sent;
        manager.sendRequest("/private", AccountManagerAuth::Required,
            QNetworkAccessManager::PostOperation, callback, {}, multipart, {});
        events(); events();
        assert(sent == before && !multipart);
    }
    manager._authURL = QUrl("https://api.invalid");
    for (auto operation : {QNetworkAccessManager::GetOperation, QNetworkAccessManager::PostOperation,
            QNetworkAccessManager::PutOperation, QNetworkAccessManager::DeleteOperation}) {
        const auto before = sent;
        manager.sendRequest("/private", AccountManagerAuth::Required, operation, callback, {}, nullptr, {});
        assert(sent == before + 1);
        assert(transport.observedOperation == (operation == QNetworkAccessManager::DeleteOperation ?
            QNetworkAccessManager::CustomOperation : operation));
        assert(transport.observed.rawHeader(ACCESS_TOKEN_AUTHORIZATION_HEADER) == "Bearer token-canary");
        assert(transport.observed.attribute(QNetworkRequest::RedirectPolicyAttribute).toInt() ==
            QNetworkRequest::ManualRedirectPolicy);
        transport.last->finish(); events();
    }
    AddressManager addresses;
    addresses.setClientLookupVisibility(false);
    assert(!addresses.apiCallbackParameters().requestTicket.current());
    assert(!addresses._lookupNeedsExplicitIntent); // initial inactive is not a resume
    addresses.setClientLookupVisibility(true);
    auto lookup = addresses.apiCallbackParameters().requestTicket;
    assert(lookup.current());
    addresses.setClientLookupVisibility(true); assert(lookup.current());
    addresses._previousAPILookup = QUrl("test-only:previous");
    addresses.setClientLookupVisibility(false);
    assert(!lookup.current() && addresses._lookupNeedsExplicitIntent && addresses._previousAPILookup.isEmpty());
    addresses.setClientLookupVisibility(true);
    assert(addresses._lookupNeedsExplicitIntent); // foreground observation does not recreate previous work
    auto newer = addresses.apiCallbackParameters().requestTicket;
    assert(newer.current() && !lookup.current());
    std::thread foreign([&] { addresses.setClientLookupVisibility(false); }); foreign.join();
    events(); assert(!newer.current()); // actual typed queued visibility invocation
    overte::network::RequestScope concurrent;
    std::vector<overte::network::RequestTicket> tickets(2000);
    std::thread first([&] { for (int i=0; i<1000; ++i) { tickets[i] = concurrent.next(); } });
    std::thread second([&] { for (int i=1000; i<2000; ++i) { tickets[i] = concurrent.next(); } });
    first.join(); second.join();
    int live = 0; for (const auto& ticket : tickets) { live += ticket.current() ? 1 : 0; }
    assert(live == 1);
}
#include "request-cancellation-test.moc"
