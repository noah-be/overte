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

Q_LOGGING_CATEGORY(networking, "overte.test.account-context")
const QString ACCOUNT_MANAGER_REQUESTED_SCOPE = "owner";
struct DataServerAccountInfo {
    struct Token { QString token, refreshToken; } token;
    QJsonObject fields;
    const Token& getAccessToken() const { return token; }
    bool hasProfile() const { return false; }
    void setAccessTokenFromJSON(const QJsonObject& object) { fields = object; token.token = object.value("access_token").toString(); }
};
Q_DECLARE_METATYPE(DataServerAccountInfo)
class Reply : public QNetworkReply {
    QByteArray payload { "{\"access_token\":\"token-canary\",\"expires_in\":3600,\"token_type\":\"Bearer\"}" };
    qint64 offset = 0;
public:
    explicit Reply(const QNetworkRequest& request, QObject* parent) : QNetworkReply(parent) {
        setUrl(request.url()); setAttribute(QNetworkRequest::HttpStatusCodeAttribute, 200);
        open(QIODevice::ReadOnly | QIODevice::Unbuffered);
    }
    void finish() { setFinished(true); emit finished(); }
    void abort() override { finish(); } // NoError success from stale abort must still be rejected.
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
    std::function<void()> onPost;
    static NetworkAccessManager& getInstance() { static NetworkAccessManager instance; return instance; }
protected:
    QNetworkReply* createRequest(Operation, const QNetworkRequest& request, QIODevice*) override {
        last = new Reply(request, this);
        if (onPost) { auto action = std::move(onPost); onPost = {}; action(); }
        return last;
    }
};
class AccountManager : public QObject {
    Q_OBJECT
public:
    overte::network::RequestScope _credentialContext;
    DataServerAccountInfo _accountInfo;
    QUrl _authURL { "https://first-private.invalid" };
    bool _isWaitingForTokenRefresh = false, _isAgent = false;
    int _numPullRetries = 3, persisted = 0, profiles = 0, removed = 0, saved = 0;
    struct Settings { int calls = 0; void loggedOut() { ++calls; } } _settings;
    QString _userAgentGetter() { return "context-test"; }
    QString getMetaverseServerURLPath() { return "/api"; }
    std::function<void()> onPersist;
    void persistAccountToFile() {
        ++persisted;
        if (onPersist) { auto action = std::move(onPersist); onPersist = {}; action(); }
    }
    void requestProfile() { ++profiles; }
    void postAccountSettings() {}
    void removeAccountFromFile() { ++removed; }
    void saveLoginStatus(bool value) { assert(!value); ++saved; }
    QMap<QString, QVariant> accountMapFromFile(bool& loaded) { loaded = false; return {}; }
    bool needsToRefreshToken() { return false; }
    bool isLoggedIn() { return false; }
    void logout();
    void setAuthURL(const QUrl&);
    void requestAccessToken(const QString&, const QString&);
    void refreshAccessToken();
public slots:
    void requestAccessTokenFinished();
    void refreshAccessTokenFinished();
    void refreshAccessTokenError(QNetworkReply::NetworkError);
signals:
    void loginComplete(QUrl);
    void loginFailed();
    void logoutComplete();
    void usernameChanged(QString);
    void authRequired();
    void authEndpointChanged();
};
#include "context.inc"
#include "context.moc"

int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    auto& network = NetworkAccessManager::getInstance();
    for (int transition = 0; transition < 3; ++transition) {
        AccountManager manager;
        int success = 0, failure = 0;
        QObject::connect(&manager, &AccountManager::loginComplete, [&] { ++success; });
        QObject::connect(&manager, &AccountManager::loginFailed, [&] { ++failure; });
        manager.requestAccessToken("user", "password");
        QPointer<Reply> stale(network.last);
        if (transition == 0) manager.logout();
        else {
            manager.setAuthURL(QUrl("https://second-private.invalid"));
            if (transition == 2) manager.setAuthURL(QUrl("https://first-private.invalid")); // ABA.
        }
        stale->finish();
        assert(success == 0 && failure == 0 && manager.persisted == 0 && manager.profiles == 0);
        assert(manager._accountInfo.token.token.isEmpty());
        if (transition == 0) assert(manager.removed == 1 && manager.saved == 1 && manager._settings.calls == 1);
        manager.requestAccessToken("user", "password");
        manager.setAuthURL(manager._authURL); // Same URL is not a context transition.
        network.last->finish();
        assert(success == 1 && manager.persisted == 1 && manager.profiles == 1);
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
        assert(!stale);
    }
    AccountManager manager;
    manager._accountInfo.token.refreshToken = "old-refresh";
    manager.refreshAccessToken();
    QPointer<Reply> staleRefresh(network.last);
    manager.logout();
    manager._accountInfo.token.refreshToken = "new-refresh";
    manager.refreshAccessToken();
    QPointer<Reply> currentRefresh(network.last);
    assert(manager._isWaitingForTokenRefresh);
    QObject::connect(staleRefresh.data(), &QNetworkReply::errorOccurred, &manager, &AccountManager::refreshAccessTokenError);
    emit staleRefresh->errorOccurred(QNetworkReply::OperationCanceledError);
    assert(manager._isWaitingForTokenRefresh);
    staleRefresh->finish();
    assert(manager._isWaitingForTokenRefresh && manager.persisted == 0);
    currentRefresh->finish();
    assert(!manager._isWaitingForTokenRefresh && manager.persisted == 1);
    network.onPost = [&] { manager.logout(); }; // Context changes inside the actual POST seam.
    manager.requestAccessToken("user", "password");
    network.last->finish();
    assert(manager.persisted == 1 && manager._accountInfo.token.token.isEmpty());
    for (bool changeServer : {false, true}) {
        AccountManager reentrant;
        int success = 0;
        QObject::connect(&reentrant, &AccountManager::loginComplete, [&] {
            ++success;
            if (changeServer) reentrant.setAuthURL(QUrl("https://replacement-private.invalid"));
            else reentrant.logout();
        });
        reentrant.requestAccessToken("user", "password");
        network.last->finish();
        assert(success == 1 && reentrant.persisted == 0 && reentrant.profiles == 0);
        assert(reentrant._accountInfo.token.token.isEmpty());
    }
    QPointer<AccountManager> destroyed = new AccountManager;
    QObject::connect(destroyed.data(), &AccountManager::loginComplete, [&] { delete destroyed.data(); });
    destroyed->requestAccessToken("user", "password");
    network.last->finish();
    assert(!destroyed);
    for (bool changeServer : {false, true}) {
        AccountManager reentrant;
        reentrant.onPersist = [&] {
            if (changeServer) reentrant.setAuthURL(QUrl("https://replacement-private.invalid"));
            else reentrant.logout();
        };
        reentrant.requestAccessToken("user", "password");
        network.last->finish();
        assert(reentrant.persisted == 1 && reentrant.profiles == 0);
        assert(reentrant._accountInfo.token.token.isEmpty());
    }
    destroyed = new AccountManager;
    destroyed->onPersist = [&] { delete destroyed.data(); };
    destroyed->requestAccessToken("user", "password");
    network.last->finish();
    assert(!destroyed);
}
