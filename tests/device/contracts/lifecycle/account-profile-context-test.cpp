#include <QtCore/QCoreApplication>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QLoggingCategory>
#include <QtCore/QPointer>
#include <QtNetwork/QNetworkAccessManager>
#include "libraries/networking/src/RequestCancellation.h"
#include "security/redaction/SafeDiagnostics.h"
#include <cassert>
#include <cstring>
#include <functional>

Q_LOGGING_CATEGORY(networking, "overte.test.profile-context")
const QByteArray ACCESS_TOKEN_AUTHORIZATION_HEADER = "Authorization";
class Reply : public QNetworkReply {
    qint64 offset = 0;
public:
    QByteArray payload = "{\"status\":\"success\",\"data\":{\"user\":{\"username\":\"new-user\"}}}";
    explicit Reply(const QNetworkRequest& request, QObject* parent) : QNetworkReply(parent) {
        setUrl(request.url()); setAttribute(QNetworkRequest::HttpStatusCodeAttribute, 200);
        open(QIODevice::ReadOnly | QIODevice::Unbuffered);
    }
    void finish() { setFinished(true); emit finished(); }
    void status(int value) { setAttribute(QNetworkRequest::HttpStatusCodeAttribute, value); }
    void fail() { setError(QNetworkReply::ConnectionRefusedError, "private-error"); }
    void abort() override { finish(); }
    qint64 bytesAvailable() const override { return payload.size() - offset + QNetworkReply::bytesAvailable(); }
    qint64 readData(char* destination, qint64 size) override {
        size = qMin(size, qint64(payload.size()) - offset);
        if (!size) return -1;
        std::memcpy(destination, payload.constData() + offset, size_t(size)); offset += size; return size;
    }
};
class NetworkAccessManager : public QNetworkAccessManager {
public:
    Reply* last = nullptr;
    QNetworkRequest observed;
    static NetworkAccessManager& getInstance() { static NetworkAccessManager instance; return instance; }
protected:
    QNetworkReply* createRequest(Operation operation, const QNetworkRequest& request, QIODevice*) override {
        assert(operation == GetOperation);
        observed = request; last = new Reply(request, this); return last;
    }
};
// Account data and persistence are explicit boundaries; real transport/request,
// QObject signals, tickets and complete production methods are compiled below.
struct AccountInfo {
    struct Token { QByteArray authorizationHeaderValue() const { return "Bearer token-canary"; } } token;
    QString username = "previous-user";
    const Token& getAccessToken() const { return token; }
    const QString& getUsername() const { return username; }
    void setProfileInfoFromJSON(const QJsonObject& object) {
        username = object["data"].toObject()["user"].toObject()["username"].toString();
    }
};
class AccountManager : public QObject {
    Q_OBJECT
public:
    overte::network::RequestScope _credentialContext, _profileContext;
    AccountInfo _accountInfo;
    bool _isWaitingForAccessToken = false;
    QUrl _authURL { "https://private-profile.invalid" };
    int persisted = 0;
    QString _userAgentGetter() { return "profile-test"; }
    QString getMetaverseServerURLPath() { return "/api"; }
    std::function<void()> onPersist;
    void persistAccountToFile() { ++persisted; if (onPersist) onPersist(); }
    void requestProfile();
public slots:
    void requestProfileFinished();
    void requestProfileError(QNetworkReply::NetworkError);
signals:
    void profileChanged();
    void usernameChanged(QString);
};
#include "profile.inc"
#include "profile.moc"

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    auto& network = NetworkAccessManager::getInstance();
    AccountManager manager;
    int profile = 0, username = 0;
    QObject::connect(&manager, &AccountManager::profileChanged, [&] { ++profile; });
    QObject::connect(&manager, &AccountManager::usernameChanged, [&] { ++username; });
    manager.requestProfile();
    QPointer<Reply> old(network.last);
    manager._credentialContext.next(); // Original login/logout/server intent boundary.
    old->finish();
    assert(manager.persisted == 0 && profile == 0 && username == 0);
    assert(manager._accountInfo.username == "previous-user");
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    assert(!old);
    manager.requestProfile(); network.last->finish();
    assert(manager.persisted == 1 && profile == 1 && username == 1);
    assert(manager._accountInfo.username == "new-user");
    network.last->finish(); // Duplicate terminal delivery does not repeat side effects.
    assert(manager.persisted == 1 && profile == 1 && username == 1);
    assert(network.observed.attribute(QNetworkRequest::RedirectPolicyAttribute).toInt() == QNetworkRequest::ManualRedirectPolicy);
    assert(network.observed.rawHeader(ACCESS_TOKEN_AUTHORIZATION_HEADER) == "Bearer token-canary");
    QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    for (bool oldFirst : {false, true}) {
        AccountManager target;
        target.requestProfile(); QPointer<Reply> stale(network.last);
        stale->payload.replace("new-user", "stale-user");
        target.requestProfile(); QPointer<Reply> current(network.last);
        if (oldFirst) stale->finish();
        current->finish();
        if (!oldFirst) stale->finish();
        assert(target.persisted == 1 && target._accountInfo.username == "new-user");
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
        assert(!stale && !current);
    }
    for (int invalid = 0; invalid < 9; ++invalid) {
        AccountManager target;
        target.requestProfile(); QPointer<Reply> reply(network.last);
        if (invalid == 0) reply->payload = "[]";
        if (invalid == 1) reply->payload = "{";
        if (invalid == 2) reply->payload = "{\"status\":\"success\"}";
        if (invalid == 3) reply->payload.replace("\"new-user\"", "42");
        if (invalid == 4) reply->status(302);
        if (invalid == 5) reply->fail();
        if (invalid == 6) reply->payload.append(QByteArray(1024 * 1024, ' '));
        if (invalid == 7) reply->setProperty("_overte_account_auth_timed_out", true);
        if (invalid == 8) reply->setProperty("_overte_profile_credentials", QVariant());
        reply->finish();
        assert(target.persisted == 0 && target._accountInfo.username == "previous-user");
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
        assert(!reply);
    }
    // An outward callback may invalidate credentials, replace the profile
    // request or destroy the manager. No following username signal is allowed.
    for (int transition = 0; transition < 3; ++transition) {
        QPointer<AccountManager> target = new AccountManager;
        int named = 0;
        QObject::connect(target.data(), &AccountManager::usernameChanged, [&] { ++named; });
        QObject::connect(target.data(), &AccountManager::profileChanged, [&] {
            if (transition == 0) target->_credentialContext.next();
            else if (transition == 1) target->requestProfile();
            else delete target.data();
        });
        target->requestProfile(); network.last->finish();
        assert(named == 0);
        delete target.data();
    }
    AccountManager failedStore;
    int published = 0;
    failedStore.onPersist = [&] { failedStore._credentialContext.next(); };
    QObject::connect(&failedStore, &AccountManager::profileChanged, [&] { ++published; });
    failedStore.requestProfile(); network.last->finish();
    assert(failedStore.persisted == 1 && published == 0);
}
