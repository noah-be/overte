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
    void token(const QString& value) {
        payload = QJsonDocument(QJsonObject {{"access_token", value}, {"expires_in", 3600},
                                            {"token_type", "Bearer"}}).toJson();
    }
    void reject() { payload = "{}"; }
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
    QList<QPointer<Reply>> created;
    std::function<void()> onPost;
    static NetworkAccessManager& getInstance() { static NetworkAccessManager instance; return instance; }
protected:
    QNetworkReply* createRequest(Operation, const QNetworkRequest& request, QIODevice*) override {
        auto* reply = new Reply(request, this);
        created.append(reply);
        last = reply;
        if (onPost) { auto action = std::move(onPost); onPost = {}; action(); }
        return reply;
    }
};
class AccountManager : public QObject {
    Q_OBJECT
public:
    overte::network::RequestScope _credentialContext;
    DataServerAccountInfo _accountInfo;
    QUrl _authURL { "https://first-private.invalid" };
    bool _isWaitingForTokenRefresh = false, _isWaitingForAccessToken = false, _isAgent = false;
    int _numPullRetries = 3, persisted = 0, profiles = 0, removed = 0, saved = 0;
    struct Settings { int calls = 0; void loggedOut() { ++calls; } } _settings;
    void resetAccountSettings() { _numPullRetries = 0; _settings.loggedOut(); }
    std::function<void()> onUserAgent;
    QString _userAgentGetter() {
        if (onUserAgent) { auto action = std::move(onUserAgent); onUserAgent = {}; action(); }
        return "context-test";
    }
    QString getMetaverseServerURLPath() { return "/api"; }
    std::function<void()> onPersist;
    void persistAccountToFile() {
        ++persisted;
        if (onPersist) { auto action = std::move(onPersist); onPersist = {}; action(); }
    }
    void requestProfile() { ++profiles; }
    std::function<void()> onSettingsPost;
    void postAccountSettings() {
        if (onSettingsPost) { auto action = std::move(onSettingsPost); onSettingsPost = {}; action(); }
    }
    void removeAccountFromFile() { ++removed; }
    bool savedValue = true;
    void saveLoginStatus(bool value) { savedValue = value; ++saved; }
    QMap<QString, QVariant> accountMapFromFile(bool& loaded) { loaded = false; return {}; }
    bool needsToRefreshToken() { return false; }
    bool isLoggedIn() { return false; }
    void logout();
    void setAuthURL(const QUrl&);
    void requestAccessToken(const QString&, const QString&);
    void requestAccessTokenWithAuthCode(const QString&, const QString&, const QString&, const QString&);
    void requestAccessTokenWithSteam(QByteArray);
    void requestAccessTokenWithOculus(const QString&, const QString&);
    bool setAccessTokens(const QString&);
    void refreshAccessToken();
public slots:
    void requestAccessTokenFinished();
    void refreshAccessTokenFinished();
    void refreshAccessTokenError(QNetworkReply::NetworkError);
#ifdef OVERTE_ACCOUNT_HAS_ERROR_SLOT
    void requestAccessTokenError(QNetworkReply::NetworkError);
#endif
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
    {
        AccountManager refreshing;
        refreshing._accountInfo.token.refreshToken = "refresh";
        refreshing.refreshAccessToken();
        network.last->finish();
        assert(refreshing._settings.calls == 0);
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
    }
    for (bool destroy : {false, true}) {
        QPointer<AccountManager> target = new AccountManager;
        target->onSettingsPost = [&] {
            if (destroy) delete target.data();
            else target->_credentialContext.next();
        };
        target->logout();
        if (target) assert(target->removed == 0 && target->saved == 0 && target->_settings.calls == 0);
        delete target.data();
    }
    auto start = [](AccountManager& target, int provider) {
        switch (provider) {
            case 0: target.requestAccessToken("user", "password"); break;
            case 1: target.requestAccessTokenWithAuthCode("code", "client", "secret", "callback"); break;
            case 2: target.requestAccessTokenWithSteam("ticket"); break;
            case 3: target.requestAccessTokenWithOculus("nonce", "id"); break;
            case 4:
                target._accountInfo.token.refreshToken = "refresh";
                target.refreshAccessToken();
                break;
        }
    };
    // A newer login intent on the SAME endpoint supersedes an older reply,
    // even when the older transport completes last with valid credentials.
    for (int firstProvider = 0; firstProvider < 4; ++firstProvider) {
    for (int nextProvider = 0; nextProvider < 4; ++nextProvider) {
    for (bool olderFirst : {false, true}) {
        AccountManager overlapping;
        int success = 0, failure = 0;
        QObject::connect(&overlapping, &AccountManager::loginComplete, [&] { ++success; });
        QObject::connect(&overlapping, &AccountManager::loginFailed, [&] { ++failure; });
        start(overlapping, firstProvider);
        QPointer<Reply> older(network.last);
        older->token("older-token");
        start(overlapping, nextProvider);
        QPointer<Reply> newer(network.last);
        newer->token("newer-token");
        overlapping._accountInfo.token.refreshToken = "previous-refresh";
        overlapping.refreshAccessToken();
        assert(network.last == newer && overlapping._isWaitingForAccessToken);
        if (olderFirst) older->finish();
        newer->finish();
        if (!olderFirst) older->finish();
        assert(success == 1 && failure == 0);
        assert(overlapping.persisted == 1 && overlapping.profiles == 1);
        assert(overlapping._accountInfo.token.token == "newer-token");
        assert(!overlapping._isWaitingForAccessToken);
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
        assert(!older && !newer);
    }
    }
    }
    const QString direct = "{\"access_token\":\"direct-token\",\"expires_in\":3600,\"token_type\":\"Bearer\"}";
    for (int provider = 0; provider < 4; ++provider) {
        AccountManager target;
        int success = 0, failure = 0;
        QObject::connect(&target, &AccountManager::loginComplete, [&] { ++success; });
        QObject::connect(&target, &AccountManager::loginFailed, [&] { ++failure; });
        target._accountInfo.token.refreshToken = "refresh";
        target.refreshAccessToken();
        QPointer<Reply> oldRefresh(network.last);
        target.refreshAccessToken(); // No parallel duplicate refresh.
        assert(network.last == oldRefresh);
        start(target, provider);
        QPointer<Reply> oldLogin(network.last);
        assert(target.setAccessTokens(direct));
        oldRefresh->finish(); oldLogin->finish();
        assert(success == 1 && failure == 0 && target.persisted == 1 && target.profiles == 1);
        assert(target._accountInfo.token.token == "direct-token");
        assert(!target._isWaitingForAccessToken && !target._isWaitingForTokenRefresh);
        start(target, provider);
        QPointer<Reply> rejected(network.last);
        rejected->reject(); rejected->finish();
        assert(success == 1 && failure == 1 && !target._isWaitingForAccessToken);
        assert(target._accountInfo.token.token == "direct-token");
        // The current failure frees admission, but cannot revive a stale reply.
        start(target, provider); network.last->token("recovery"); network.last->finish();
        assert(success == 2 && target._accountInfo.token.token == "recovery");
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
        assert(!oldRefresh && !oldLogin && !rejected);
    }
    for (bool postBoundary : {false, true}) {
    for (int provider = 0; provider < 5; ++provider) {
        // Current reply destruction frees admission; destroying an old reply
        // must not clear the newer owner's pending state.
        AccountManager lifetime;
        start(lifetime, 0); QPointer<Reply> old(network.last);
        start(lifetime, 1); QPointer<Reply> current(network.last);
        delete old.data();
        assert(lifetime._isWaitingForAccessToken);
        delete current.data();
        assert(!lifetime._isWaitingForAccessToken);
        lifetime._accountInfo.token.refreshToken = "refresh";
        lifetime.refreshAccessToken();
        delete network.last;
        assert(!lifetime._isWaitingForTokenRefresh);
        AccountManager target;
        auto replacement = [&] { start(target, 1); };
        if (postBoundary) network.onPost = replacement;
        else target.onUserAgent = replacement;
        const auto beforeReplacement = network.created.size();
        start(target, provider);
        network.last->token("reentrant-new"); network.last->finish();
        assert(target.persisted == 1 && target._accountInfo.token.token == "reentrant-new");
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
        if (postBoundary) assert(!network.created[beforeReplacement]);
        QPointer<AccountManager> deleted = new AccountManager;
        auto destroy = [&] { delete deleted.data(); };
        if (postBoundary) network.onPost = destroy;
        else deleted->onUserAgent = destroy;
        const auto beforeDestruction = network.created.size();
        start(*deleted, provider);
        assert(!deleted);
        QCoreApplication::sendPostedEvents(nullptr, QEvent::DeferredDelete);
        if (postBoundary) assert(!network.created[beforeDestruction]);
    }
    }
    for (bool imported : {false, true}) {
        AccountManager target;
        bool replace = true;
        QObject::connect(&target, &AccountManager::loginComplete, [&] {
            if (replace) { replace = false; start(target, 2); }
        });
        if (imported) assert(!target.setAccessTokens(direct));
        else { start(target, 0); network.last->finish(); }
        assert(target.persisted == 1 && target.profiles == 0 && target.saved == 0);
        network.last->token("replacement"); network.last->finish();
        assert(target.persisted == 2 && target.profiles == 1);
        assert(target._accountInfo.token.token == "replacement");
    }
    {
        AccountManager target;
        target._accountInfo.token.refreshToken = "refresh";
        target.refreshAccessToken();
        QPointer<Reply> old(network.last);
        QObject::connect(old.data(), &QNetworkReply::errorOccurred, &target, &AccountManager::refreshAccessTokenError);
        emit old->errorOccurred(QNetworkReply::OperationCanceledError);
        assert(!target._isWaitingForTokenRefresh);
        target.refreshAccessToken();
        QPointer<Reply> current(network.last);
        old->finish();
        assert(target._isWaitingForTokenRefresh && target.persisted == 0);
        current->finish();
        assert(!target._isWaitingForTokenRefresh && target.persisted == 1);
    }
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
        if (transition == 0) assert(manager.removed == 1 && manager.saved == 1 && !manager.savedValue && manager._settings.calls == 1);
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
        // Successful persistence now precedes the outward login signal. A
        // listener's logout/server change must still prevent profile startup.
        assert(success == 1 && reentrant.persisted == 1 && reentrant.profiles == 0);
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
